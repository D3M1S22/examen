"""Comprehensive unit and integration tests for the EXAMEN Serving & MCP layer.

Tests:
1. All 5 MCP tools (create_planned_task, verify_action_status, get_daily_actions_recap,
   query_social_contact, get_topic_briefing).
2. Starlette REST API endpoints (/api/status, /api/actions, /api/routines, /api/contacts, /api/topics).
3. Web UI static files serving (/ and /ext-app).
"""

import os
import tempfile
import pytest
from datetime import datetime
from starlette.testclient import TestClient

from src.core.schemas import (
    BriefingReport,
    PlannedTask,
    SocialCommitment,
    MicroEventRef,
    SessionDossier,
    SocialEntity,
    SocialWebProfile,
    VerifiedAction,
)
from src.core.storage.sqlite_store import SQLiteContextStore
from src.serving.mcp_server import create_app
from src.serving.tools.action_tools import (
    execute_create_planned_task,
    execute_get_daily_actions_recap,
    execute_get_upcoming_tasks,
    execute_verify_action_status,
    _format_elapsed_time,
)
from src.serving.tools.social_tools import (
    execute_get_contact_profile,
    execute_get_social_commitments,
    execute_query_social_contact,
    get_contact_profile,
)
from src.serving.tools.topic_tools import execute_get_topic_briefing
from src.serving.tools.session_tools import (
    execute_get_session_dossier,
    execute_list_session_dossiers,
)
from src.core.storage import get_storage_store


@pytest.fixture
def temp_store():
    """Provides a fresh isolated SQLiteContextStore for serving tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = SQLiteContextStore(db_path=db_path)
    yield store
    store.close()
    if os.path.exists(db_path):
        os.remove(db_path)


class TestActionServingTools:
    """Tests for domestic safety, action verifications, and routine tools."""

    def test_create_planned_task(self, temp_store):
        res = execute_create_planned_task(
            title="Unplug clothes iron",
            domain="safety",
            scheduled_time="08:30",
            recurrence="daily",
            store=temp_store,
        )
        assert res["status"] == "scheduled"
        assert res["title"] == "Unplug clothes iron"
        assert res["domain"] == "safety"
        assert res["scheduled_time"] == "08:30"
        assert res["tracking_status"] == "watching_ambient_stream"

        # Verify persisted in store
        task = temp_store.get_planned_task(res["task_id"])
        assert task is not None
        assert task.status == "pending"

    def test_verify_action_status_found(self, temp_store):
        now_iso = datetime.now().isoformat()
        action = VerifiedAction(
            action_type="iron_unplugged",
            domain="safety",
            confidence=0.96,
            raw_statement="I unplugged the clothes iron before leaving",
            timestamp=now_iso,
        )
        temp_store.save_action(action)

        res = execute_verify_action_status(action_query="iron", store=temp_store)
        assert res["status"] == "verified"
        assert res["action_type"] == "iron_unplugged"
        assert res["confidence"] == 0.96
        assert res["ui_card_type"] == "ACTION_VERIFIED_BADGE"
        assert "just now" in res["elapsed_time_human"].lower() or "ago" in res["elapsed_time_human"].lower()
        assert "spoken_summary" in res

    def test_verify_action_status_not_found(self, temp_store):
        res = execute_verify_action_status(action_query="spacecraft_launched", store=temp_store)
        assert res["status"] == "unverified"
        assert res["ui_card_type"] == "ACTION_UNVERIFIED_BADGE"
        assert "No verified completion" in res["message"]

    def test_get_daily_actions_recap(self, temp_store):
        # 1. Add planned task
        task = PlannedTask(title="Lock front door", domain="safety", status="pending")
        task_id = temp_store.save_planned_task(task)

        # 2. Add spontaneous action
        action = VerifiedAction(
            action_type="merged_pr",
            domain="work_task",
            confidence=0.92,
            raw_statement="Merged pull request #42",
            timestamp=datetime.now().isoformat(),
        )
        temp_store.save_action(action)

        recap = execute_get_daily_actions_recap(store=temp_store)
        assert recap["summary"]["planned_total"] == 1
        assert recap["summary"]["planned_pending"] == 1
        assert recap["summary"]["planned_completed"] == 0
        assert recap["summary"]["spontaneous_actions"] == 1
        assert len(recap["planned_routines"]) == 1
        assert len(recap["spontaneous_actions"]) == 1

        # Now complete the planned task
        temp_store.complete_planned_task(task_id=task_id, verified_action_id="act-123")
        recap_updated = execute_get_daily_actions_recap(store=temp_store)
        assert recap_updated["summary"]["planned_completed"] == 1
        assert recap_updated["summary"]["planned_pending"] == 0

    def test_get_upcoming_tasks(self, temp_store):
        t1 = PlannedTask(
            title="Manual Task",
            domain="routine",
            scheduled_time="2026-10-09T08:00:00",
            origin="manual",
            status="pending",
        )
        t2 = PlannedTask(
            title="Call Dr. Smith",
            domain="personal",
            scheduled_time="2026-10-09T15:00:00",
            origin="ambient_voice",
            raw_statement="I need to call Dr. Smith at 3 PM tomorrow.",
            confidence=0.95,
            relative_time_anchor="at 3 PM tomorrow",
            status="pending",
        )
        t3 = PlannedTask(
            title="Old Completed Task",
            domain="safety",
            origin="ambient_voice",
            status="completed",
        )
        temp_store.save_planned_task(t1)
        temp_store.save_planned_task(t2)
        temp_store.save_planned_task(t3)

        res = execute_get_upcoming_tasks(store=temp_store)
        assert res["count"] == 2
        assert res["ui_card_type"] == "UPCOMING_TASKS_VIEWER"
        titles = [task["title"] for task in res["tasks"]]
        assert "Manual Task" in titles
        assert "Call Dr. Smith" in titles
        assert "Old Completed Task" not in titles

        # Filter by domain
        res_personal = execute_get_upcoming_tasks(domain="personal", store=temp_store)
        assert res_personal["count"] == 1
        assert res_personal["tasks"][0]["origin"] == "ambient_voice"
        assert res_personal["tasks"][0]["raw_statement"] == "I need to call Dr. Smith at 3 PM tomorrow."

    def test_format_elapsed_time(self):
        now_iso = datetime.now().isoformat()
        assert _format_elapsed_time(now_iso) == "just now"
        # Test malformed
        assert _format_elapsed_time("not-a-date") == "not-a-date"


class TestSocialServingTools:
    """Tests for relational memory and social contact tools."""

    def test_query_social_contact_found(self, temp_store):
        contact = SocialEntity(
            person_name="Marco Rossi",
            company_or_role="Tech Lead @ Acme Corp",
            contact_info="marco@acme.com",
            commitments=["Send architecture link", "Schedule call for Friday"],
            key_topics=["Bedrock", "AgentCore", "AI"],
            timestamp="2026-10-01T10:30:00",
        )
        temp_store.save_social_contact(contact)

        res = execute_query_social_contact(name_or_query="Marco", store=temp_store)
        assert res["found"] is True
        assert res["contact"]["name"] == "Marco Rossi"
        assert res["contact"]["company_or_role"] == "Tech Lead @ Acme Corp"
        assert len(res["contact"]["commitments"]) == 2
        assert res["ui_card_type"] == "SOCIAL_PROFILE_CARD"
        assert "Marco Rossi" in res["spoken_summary"]

    def test_query_social_contact_not_found(self, temp_store):
        res = execute_query_social_contact(name_or_query="NonExistentPerson", store=temp_store)
        assert res["found"] is False
        assert res["ui_card_type"] == "SOCIAL_NOT_FOUND"
        assert "No social contact found" in res["message"]

    def test_get_social_commitments_tool(self, temp_store):
        # Seed user commitment
        c1 = SocialCommitment(
            contact_name="Sara Bianchi",
            debtor="user",
            description="Send product brochure",
            due_date_raw="tomorrow morning",
            status="open",
        )
        temp_store.save_social_commitment(c1)

        # Seed contact commitment
        c2 = SocialCommitment(
            contact_name="Sara Bianchi",
            debtor="contact",
            description="Introduce technical co-founder",
            status="open",
        )
        temp_store.save_social_commitment(c2)

        # Query all
        res = execute_get_social_commitments(contact_name="Sara Bianchi", store=temp_store)
        assert res["found"] is True
        assert res["total"] == 2
        assert res["user_promises_count"] == 1
        assert res["contact_promises_count"] == 1
        assert res["ui_card_type"] == "SOCIAL_COMMITMENTS_CARD"
        assert "Sara Bianchi" in res["spoken_summary"]
        assert "brochure" in res["spoken_summary"]

        # Filter by debtor='user'
        user_res = execute_get_social_commitments(debtor="user", store=temp_store)
        assert user_res["total"] == 1
        assert user_res["commitments"][0]["debtor"] == "user"

        # Filter by non-existent status
        empty_res = execute_get_social_commitments(status="cancelled", store=temp_store)
        assert empty_res["found"] is False

    def test_get_contact_profile_tool(self, temp_store):
        # 1. Non-existent contact
        not_found = execute_get_contact_profile("NonExistentContact", store=temp_store)
        assert not_found["found"] is False
        assert not_found["ui_card_type"] == "SOCIAL_NOT_FOUND"

        # 2. Existing contact with web profile
        contact = SocialEntity(
            person_name="Luca Bianchi",
            company_or_role="VP of Infrastructure at CloudScale",
            contact_info="luca@cloudscale.io",
            key_topics=["Distributed Systems"],
            web_profile=SocialWebProfile(
                headline="VP of Infrastructure at CloudScale | ex-AWS",
                organization="CloudScale",
                current_role="VP of Infrastructure",
                bio_summary="Luca Bianchi oversees cloud infrastructure at CloudScale.",
                areas_of_expertise=["Distributed Systems", "Kubernetes", "AWS Architecture"],
                linkedin_url="https://www.linkedin.com/in/luca-bianchi-cloud",
                confidence_score=0.98,
            ),
        )
        temp_store.save_social_contact(contact)

        res = execute_get_contact_profile("Luca Bianchi", store=temp_store)
        assert res["found"] is True
        assert res["ui_card_type"] == "SOCIAL_PROFILE_CARD"
        assert res["display_template"] == "SOCIAL_PROFILE_CARD"
        assert res["web_profile"]["organization"] == "CloudScale"
        assert res["web_profile"]["confidence_score"] == 0.98
        assert "Luca Bianchi" in res["spoken_summary"]
        assert "CloudScale" in res["spoken_summary"]


class TestTopicServingTools:
    """Tests for synthesized technical briefing tools."""

    def test_get_topic_briefing_found(self, temp_store):
        briefing = BriefingReport(
            topic_title="AWS Bedrock AgentCore Orchestration",
            context_type="tech_stack",
            executive_summary=[
                "AgentCore hosts serverless microVM runtimes on Graviton.",
                "Supports state persistence and native MCP protocol.",
            ],
            web_sources=["https://docs.aws.amazon.com/bedrock", "https://github.com/awslabs/bedrock-agentcore"],
            action_items=["Setup IAM execution role", "Test gatekeeper screening latency"],
            explanatory_synthesis="Bedrock AgentCore architecture utilizes firecracker microVMs for isolated execution.",
            deep_dive_markdown="# Deep Dive on AgentCore\n\nFull architecture analysis...",
            created_at=datetime.now().isoformat(),
        )
        temp_store.save_topic_briefing(briefing)

        res = execute_get_topic_briefing(topic_query="AgentCore", store=temp_store)
        assert res["found"] is True
        assert res["topic_title"] == "AWS Bedrock AgentCore Orchestration"
        assert len(res["executive_summary"]) == 2
        assert len(res["web_sources"]) == 2
        assert res["explanatory_synthesis"] == "Bedrock AgentCore architecture utilizes firecracker microVMs for isolated execution."
        assert res["ui_card_type"] == "DEEP_BRIEFING_VIEWER"
        assert "spoken_summary" in res

    def test_get_topic_briefing_latest(self, temp_store):
        b1 = BriefingReport(
            topic_title="Early Topic",
            context_type="tech_stack",
            executive_summary=["First"],
            created_at="2026-10-01T08:00:00",
        )
        b2 = BriefingReport(
            topic_title="Latest Topic",
            context_type="tech_stack",
            executive_summary=["Second"],
            created_at="2026-10-02T10:00:00",
        )
        temp_store.save_topic_briefing(b1)
        temp_store.save_topic_briefing(b2)

        res = execute_get_topic_briefing(topic_query=None, store=temp_store)
        assert res["found"] is True
        assert res["topic_title"] == "Latest Topic"

    def test_get_topic_briefing_not_found(self, temp_store):
        res = execute_get_topic_briefing(topic_query="QuantumAntigravityTheory", store=temp_store)
        assert res["found"] is False
        assert res["ui_card_type"] == "BRIEFING_NOT_FOUND"


class TestServerRestApiAndWebUi:
    """Tests for the Starlette app endpoints and static web UI."""

    @pytest.fixture
    def client(self):
        app = create_app()
        return TestClient(app)

    def test_api_status(self, client):
        res = client.get("/api/status")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "online"
        assert "config" in data
        assert "stats" in data
        assert "gatekeeper_provider" in data["config"]

    def test_api_actions(self, client):
        res = client.get("/api/actions")
        assert res.status_code == 200
        data = res.json()
        assert "actions" in data
        assert isinstance(data["actions"], list)

    def test_api_routines_lifecycle(self, client):
        # 1. Create a planned routine
        post_res = client.post("/api/routines", json={
            "title": "Evening blood pressure medication",
            "domain": "routine",
            "scheduled_time": "21:00",
            "recurrence": "daily",
        })
        assert post_res.status_code == 201
        created = post_res.json()
        assert created["success"] is True
        assert created["title"] == "Evening blood pressure medication"
        assert created["origin"] == "manual"

        # 2. Create an ambient voice scheduled task
        amb_res = client.post("/api/routines", json={
            "title": "Call Dr. Smith",
            "domain": "personal",
            "scheduled_time": "2026-10-09T15:00:00",
            "origin": "ambient_voice",
            "raw_statement": "I need to call Dr. Smith at 3 PM tomorrow.",
            "relative_time_anchor": "at 3 PM tomorrow",
        })
        assert amb_res.status_code == 201
        amb_data = amb_res.json()
        assert amb_data["origin"] == "ambient_voice"
        assert amb_data["raw_statement"] == "I need to call Dr. Smith at 3 PM tomorrow."

        # 3. List all planned routines
        get_res = client.get("/api/routines")
        assert get_res.status_code == 200
        tasks = get_res.json()["tasks"]
        assert any(t["title"] == "Evening blood pressure medication" for t in tasks)
        assert any(t["title"] == "Call Dr. Smith" and t["origin"] == "ambient_voice" for t in tasks)

        # 4. Filter by origin
        amb_get = client.get("/api/routines?origin=ambient_voice")
        assert amb_get.status_code == 200
        amb_tasks = amb_get.json()["tasks"]
        assert all(t["origin"] == "ambient_voice" for t in amb_tasks)
        assert any(t["title"] == "Call Dr. Smith" for t in amb_tasks)

    def test_api_routines_invalid(self, client):
        res = client.post("/api/routines", json={"domain": "safety"})
        assert res.status_code == 400

    def test_api_contacts(self, client):
        res = client.get("/api/contacts")
        assert res.status_code == 200
        data = res.json()
        assert "contacts" in data

    def test_api_topics(self, client):
        store = get_storage_store()
        briefing = BriefingReport(
            topic_title="HTTP/3 and QUIC Protocols",
            context_type="tech_stack",
            executive_summary=["0-RTT handshakes", "Multiplexing without head-of-line blocking"],
            explanatory_synthesis="QUIC replaces TCP and TLS handshakes with a UDP-based encrypted transport layer.",
            web_sources=["https://cloudflare.com/quic"],
            action_items=["Verify UDP 443 firewall access"],
        )
        store.save_topic_briefing(briefing)

        res = client.get("/api/topics")
        assert res.status_code == 200
        data = res.json()
        assert "topics" in data
        assert len(data["topics"]) >= 1
        first_topic = next((t for t in data["topics"] if t["topic_title"] == "HTTP/3 and QUIC Protocols"), None)
        assert first_topic is not None
        assert "explanatory_synthesis" in first_topic
        assert first_topic["explanatory_synthesis"] == "QUIC replaces TCP and TLS handshakes with a UDP-based encrypted transport layer."

    def test_web_ui_root(self, client):
        # With Next.js decoupled, root serves 404 unless `npm run build` has populated `out/`
        res = client.get("/")
        assert res.status_code in [200, 404]

    def test_web_ui_ext_app(self, client):
        res = client.get("/ext-app/")
        assert res.status_code in [200, 404]

    def test_web_ui_css_and_js(self, client):
        css_res = client.get("/styles.css")
        assert css_res.status_code in [200, 404]
        js_res = client.get("/app.js")
        assert js_res.status_code in [200, 404]

    def test_api_routines_update_and_delete(self, client):
        # 1. Create a task
        create_res = client.post("/api/routines", json={
            "title": "Initial Task",
            "domain": "routine",
            "scheduled_time": "08:00",
            "recurrence": "daily",
        })
        assert create_res.status_code == 201
        task_id = create_res.json()["task_id"]

        # 2. Update task
        update_res = client.put(f"/api/routines/{task_id}", json={
            "title": "Renamed Task",
            "domain": "safety",
            "scheduled_time": "08:45",
            "recurrence": "weekdays",
            "status": "pending",
        })
        assert update_res.status_code == 200
        updated = update_res.json()["task"]
        assert updated["title"] == "Renamed Task"
        assert updated["domain"] == "safety"
        assert updated["scheduled_time"] == "08:45"

        # 3. Delete task
        delete_res = client.delete(f"/api/routines/{task_id}")
        assert delete_res.status_code == 200
        assert delete_res.json()["deleted_id"] == task_id

        # 4. Updating deleted task returns 404
        assert client.put(f"/api/routines/{task_id}", json={"title": "Test"}).status_code == 404

    def test_api_routines_toggle(self, client):
        # Create a task
        create_res = client.post("/api/routines", json={
            "title": "Toggle Me",
            "domain": "safety",
        })
        task_id = create_res.json()["task_id"]

        # Toggle to completed
        t1 = client.post(f"/api/routines/{task_id}/toggle")
        assert t1.status_code == 200
        assert t1.json()["task"]["status"] == "completed"
        assert t1.json()["task"]["completed_at"] is not None

        # Toggle back to pending
        t2 = client.post(f"/api/routines/{task_id}/toggle")
        assert t2.status_code == 200
        assert t2.json()["task"]["status"] == "pending"
        assert t2.json()["task"]["completed_at"] is None

        # Cleanup
        client.delete(f"/api/routines/{task_id}")

    def test_api_events_sse(self, client):
        res = client.get("/api/events?limit=1")
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]
        assert "connected" in res.text

    def test_api_commitments_lifecycle(self, client):
        # 1. Create a commitment via API
        create_res = client.post("/api/commitments", json={
            "contact_name": "Elena Rostova",
            "debtor": "user",
            "description": "Send architecture diagram",
            "due_date_raw": "tomorrow at 10 AM",
            "normalized_deadline": "2026-10-09T10:00:00",
        })
        assert create_res.status_code == 201
        data = create_res.json()["commitment"]
        com_id = data["id"]
        assert data["contact_name"] == "Elena Rostova"
        assert data["debtor"] == "user"
        assert data["status"] == "open"
        assert data["auto_scheduled_task_id"] is not None

        # 2. Query commitments via GET
        list_res = client.get(f"/api/commitments?contact_name=Elena Rostova")
        assert list_res.status_code == 200
        comms = list_res.json()["commitments"]
        assert len(comms) >= 1
        assert comms[0]["id"] == com_id

        # 3. Fulfill commitment
        fulfill_res = client.post(f"/api/commitments/{com_id}/fulfill")
        assert fulfill_res.status_code == 200
        assert fulfill_res.json()["commitment"]["status"] == "fulfilled"

        # 4. Cancel commitment
        cancel_res = client.post(f"/api/commitments/{com_id}/cancel")
        assert cancel_res.status_code == 200
        assert cancel_res.json()["commitment"]["status"] == "cancelled"

        # 5. Verify system status reflects commitment stats
        status_res = client.get("/api/status")
        assert status_res.status_code == 200
        stats = status_res.json()["stats"]
        assert "total_commitments" in stats
        assert "open_commitments" in stats

    def test_api_contact_profile_and_enrich_endpoints(self, client):
        store = get_storage_store()

        # 1. Non-existent profile query returns 404
        assert client.get("/api/contacts/nonexistent-id/profile").status_code == 404

        # 2. Pre-seed contact with web profile
        contact = SocialEntity(
            person_name="Luca Bianchi",
            company_or_role="VP of Infrastructure at CloudScale",
            web_profile=SocialWebProfile(
                headline="VP of Infrastructure at CloudScale",
                organization="CloudScale",
                current_role="VP of Infrastructure",
                bio_summary="Luca Bianchi leads cloud infrastructure at CloudScale.",
                areas_of_expertise=["Distributed Systems", "Cloud"],
                confidence_score=0.96,
            ),
        )
        rec_id = store.save_social_contact(contact)

        # GET /api/contacts/{id}/profile returns 200
        res = client.get(f"/api/contacts/{rec_id}/profile")
        assert res.status_code == 200
        data = res.json()
        assert data["found"] is True
        assert data["web_profile"]["organization"] == "CloudScale"
        assert data["ui_card_type"] == "SOCIAL_PROFILE_CARD"

        # Also verify GET /api/contacts includes web_profile
        list_res = client.get(f"/api/contacts?q=Luca")
        assert list_res.status_code == 200
        contacts = list_res.json()["contacts"]
        assert len(contacts) >= 1
        assert contacts[0]["web_profile"] is not None
        assert contacts[0]["web_profile"]["organization"] == "CloudScale"

        # 3. Test POST /api/contacts/{id}/enrich on unenriched qualified contact
        contact_new = SocialEntity(
            person_name="Dr. Elena Rostova",
            company_or_role="Robotics Vision Lab Head at ETH Zurich",
            key_topics=["Robotics", "Computer Vision"],
            web_profile=None,
        )
        new_id = store.save_social_contact(contact_new)

        enrich_res = client.post(f"/api/contacts/{new_id}/enrich")
        assert enrich_res.status_code == 200
        enrich_data = enrich_res.json()
        assert enrich_data["success"] is True
        assert enrich_data["web_profile"] is not None

        # Verify profile is now persisted in store
        persisted = store.get_social_contact(new_id)
        assert persisted.web_profile is not None

    def test_api_single_commitment_get_and_delete(self, client):
        # 1. Create a commitment
        create_res = client.post("/api/commitments", json={
            "contact_name": "Test User",
            "debtor": "user",
            "description": "Send meeting notes",
            "due_date_raw": "today at 6 PM",
        })
        assert create_res.status_code == 201
        com_id = create_res.json()["commitment"]["id"]

        # 2. GET /api/commitments/{id}
        get_res = client.get(f"/api/commitments/{com_id}")
        assert get_res.status_code == 200
        assert get_res.json()["commitment"]["id"] == com_id
        assert get_res.json()["commitment"]["description"] == "Send meeting notes"

        # 3. DELETE /api/commitments/{id}
        del_res = client.delete(f"/api/commitments/{com_id}")
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True

        # 4. Verify 404 after deletion
        get_after = client.get(f"/api/commitments/{com_id}")
        assert get_after.status_code == 404

        # 5. Deleting non-existent commitment returns 404
        del_after = client.delete(f"/api/commitments/{com_id}")
        assert del_after.status_code == 404

    def test_api_cards_preview_templates(self, client):
        # Seed test data in store
        store = get_storage_store()
        store.save_action(VerifiedAction(
            action_type="iron_unplugged",
            domain="safety",
            raw_statement="Staccato il ferro",
            confidence=0.98,
            timestamp=datetime.now().isoformat(),
        ))
        store.save_social_contact(SocialEntity(
            person_name="Preview Contact",
            company_or_role="Lead Architect",
            commitments=["Review code"],
        ))
        store.save_planned_task(PlannedTask(
            title="Check kitchen lights",
            domain="safety",
            status="pending",
        ))

        templates = [
            "DEEP_BRIEFING_VIEWER",
            "SOCIAL_PROFILE_CARD",
            "SOCIAL_COMMITMENTS_CARD",
            "ACTION_VERIFIED_BADGE",
            "DAILY_ACTIONS_RECAP",
            "UPCOMING_TASKS_VIEWER",
        ]

        for tmpl in templates:
            res = client.get(f"/api/cards/preview?template={tmpl}")
            assert res.status_code == 200
            data = res.json()
            assert data["display_template"] == tmpl
            assert "card_payload" in data
            assert isinstance(data["card_payload"], dict)
            assert "spoken_summary" in data
            assert len(data["spoken_summary"]) > 0

    def test_serving_tools_standardized_card_payloads(self, client):
        store = get_storage_store()

        # 1. Topic briefing tool
        briefing_res = execute_get_topic_briefing(store=store)
        assert briefing_res["display_template"] == "DEEP_BRIEFING_VIEWER"
        assert "card_payload" in briefing_res
        assert "topic_title" in briefing_res["card_payload"]

        # 2. Social query tool
        social_res = execute_query_social_contact(name_or_query="Preview Contact", store=store)
        assert social_res["display_template"] == "SOCIAL_PROFILE_CARD"
        assert "card_payload" in social_res
        assert "name" in social_res["card_payload"]

        # 3. Social commitments tool
        comm_res = execute_get_social_commitments(store=store)
        assert comm_res["display_template"] == "SOCIAL_COMMITMENTS_CARD"
        assert "card_payload" in comm_res
        assert "user_debts" in comm_res["card_payload"]

        # 4. Action verify tool
        action_res = execute_verify_action_status(action_query="iron", store=store)
        assert action_res["display_template"] in ("ACTION_VERIFIED_BADGE", "ACTION_UNVERIFIED_BADGE")
        assert "card_payload" in action_res

        # 5. Daily recap tool
        recap_res = execute_get_daily_actions_recap(store=store)
        assert recap_res["display_template"] == "DAILY_ACTIONS_RECAP"
        assert "card_payload" in recap_res
        assert "total_actions" in recap_res["card_payload"]

        # 6. Upcoming tasks tool
        tasks_res = execute_get_upcoming_tasks(store=store)
        assert tasks_res["display_template"] == "UPCOMING_TASKS_VIEWER"
        assert "card_payload" in tasks_res
        assert "tasks" in tasks_res["card_payload"]

        # 7. Session dossier tool (Milestone 3.2)
        sess_res = execute_get_session_dossier(store=store)
        assert sess_res["display_template"] in ("SESSION_DOSSIER_VIEWER", "SESSION_NOT_FOUND")

    def test_api_sessions_endpoints(self, client):
        store = get_storage_store()
        sess = SessionDossier(
            session_id="sess-api-test-01",
            title="API Test Meeting",
            domain="meeting",
            status="active",
        )
        store.save_session_dossier(sess)

        # GET /api/sessions
        res = client.get("/api/sessions")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] >= 1
        assert any(s["session_id"] == "sess-api-test-01" for s in data["sessions"])

        # GET /api/sessions/{session_id}
        res_detail = client.get("/api/sessions/sess-api-test-01")
        assert res_detail.status_code == 200
        detail_data = res_detail.json()
        assert detail_data["found"] is True
        assert detail_data["title"] == "API Test Meeting"

        # POST /api/sessions/{session_id}/conclude
        res_conclude = client.post("/api/sessions/sess-api-test-01/conclude", json={})
        assert res_conclude.status_code == 200
        concl_data = res_conclude.json()
        assert concl_data["success"] is True
        assert concl_data["dossier"]["status"] == "concluded"

    def test_api_cards_preview_session_dossier(self, client):
        res = client.get("/api/cards/preview?template=SESSION_DOSSIER_VIEWER")
        assert res.status_code == 200
        data = res.json()
        assert data["display_template"] == "SESSION_DOSSIER_VIEWER"
        assert "card_payload" in data
        assert data["card_payload"]["template"] == "SESSION_DOSSIER_VIEWER"



