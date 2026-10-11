import os
import sys

# Ensure src module is discoverable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.storage import get_storage_store
from src.core.schemas import VerifiedAction, PlannedTask, SocialEntity, BriefingReport
from datetime import datetime, timedelta

def populate_mock_data():
    store = get_storage_store()
    now = datetime.now()

    print("Populating DB with mock data...")

    # Planned Tasks
    t1 = PlannedTask(
        title="Check Server Logs",
        domain="work_task",
        scheduled_time=(now + timedelta(hours=1)).isoformat(),
        recurrence="daily",
        status="pending"
    )
    t2 = PlannedTask(
        title="Lock Garage Door",
        domain="safety",
        scheduled_time=(now - timedelta(hours=2)).isoformat(),
        recurrence="daily",
        status="completed",
        completed_at=(now - timedelta(minutes=15)).isoformat()
    )
    store.save_planned_task(t1)
    store.save_planned_task(t2)
    print("Added Planned Tasks")

    # Verified Actions
    a1 = VerifiedAction(
        action_type="Garage Door Locked",
        domain="safety",
        raw_statement="Garage door is locked and secured.",
        confidence=0.99,
        timestamp=(now - timedelta(minutes=15)).isoformat(),
    )
    a2 = VerifiedAction(
        action_type="AWS EC2 Shutdown",
        domain="work_task",
        raw_statement="I just shut down the dev server to save costs.",
        confidence=0.95,
        timestamp=(now - timedelta(minutes=60)).isoformat(),
    )
    store.save_action(a1)
    store.save_action(a2)
    print("Added Verified Actions")

    # Social Entities
    s1 = SocialEntity(
        person_name="Elena Rodriguez",
        company_or_role="Cloud Architect at DataFlow",
        contact_info="elena@dataflow.ai",
        key_topics=["AWS Bedrock", "RAG architectures", "Kubernetes"],
        commitments=["Send Elena the architecture diagrams by Friday."],
        timestamp=(now - timedelta(days=1)).isoformat()
    )
    s2 = SocialEntity(
        person_name="Marcus Chen",
        company_or_role="Freelance UI/UX Designer",
        key_topics=["Figma", "Design Systems", "Web UI"],
        commitments=[],
        timestamp=(now - timedelta(days=3)).isoformat()
    )
    store.save_social_contact(s1)
    store.save_social_contact(s2)
    print("Added Social Contacts")

    # Topic Briefings
    b1 = BriefingReport(
        topic_title="Multi-agent Frameworks in Production",
        context_type="tech_stack",
        executive_summary=[
            "Multi-agent systems provide localized decision making capabilities.",
            "They significantly increase fault tolerance.",
            "State management requires careful dependency mapping."
        ],
        action_items=["Review LangGraph orchestration paradigms.", "Test Bedrock AgentCore constraints."],
        web_sources=["https://langchain-ai.github.io/langgraph/", "https://aws.amazon.com/bedrock/"],
        created_at=(now - timedelta(hours=3)).isoformat()
    )
    store.save_topic_briefing(b1)
    print("Added Topic Briefings")

    print("Data Population Complete!")

if __name__ == "__main__":
    populate_mock_data()
