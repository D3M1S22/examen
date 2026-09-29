# 🎙️ Serving Layer: Alexa+ MCP Server & Echo Show UI

> This document defines the **Serving Architecture** of **EXAMEN** *(from Latin "exāmen": swarm of bees & careful examination)*, explaining how stored context is exposed via a **Model Context Protocol (MCP)** server for **Alexa+** and rendered visually on **Echo Show** screens using the **ext-apps** framework.

---

## 🌐 Architecture of the Alexa+ MCP Server

Alexa+ interfaces with EXAMEN using the open standard **Model Context Protocol (MCP)** over **Streamable HTTP**. When the user asks a natural voice question, Alexa's LLM inspects the tools exposed by the EXAMEN MCP server, dispatches the corresponding JSON-RPC 2.0 tool call, and delivers the answer both through natural speech (TTS) and interactive on-screen cards.

```
 [ User at Home / Office ]
            │ (Spoken inquiry)
            ▼
   [ Echo Show / Alexa+ ]
            │
            ▼ (MCP Streamable HTTP / JSON-RPC 2.0)
 ┌────────────────────────────────────────────────────────┐
 │           EXAMEN MCP Server (Python FastMCP)           │
 ├────────────────────────────────────────────────────────┤
 │ 🔧 Tool: create_planned_task(title, domain, ...)       │
 │ 🔧 Tool: verify_action_status(action_query)            │
 │ 🔧 Tool: get_daily_actions_recap(date, domain)         │
 │ 🔧 Tool: query_social_contact(name_or_query)           │
 │ 🔧 Tool: get_topic_briefing(topic_query)               │
 └──────────────────────────┬─────────────────────────────┘
                            │ (Context retrieval)
                            ▼
          [ Context Store: SQLite / DynamoDB ]
```

---

## 🛠️ Exposed MCP Tool Specifications

### 1. `create_planned_task` (Routine & Task Setup)
Registers a scheduled routine or domestic safety task to be tracked and automatically resolved via ambient listening.
* **Tool Description:** *"Schedule a domestic safety check, daily routine, or planned work task with optional recurrence or scheduled time."*
* **Input Parameters:**
  - `title` *(string, required)*: Task description (e.g. `"unplug clothes iron"`, `"take blood pressure medication"`, `"backup production database"`).
  - `domain` *(string, optional, default: `"routine"`)*: Category (`"safety"`, `"routine"`, `"work_task"`).
  - `scheduled_time` *(string, optional)*: Target scheduled time (e.g. `"08:30"`, `"21:00"`).
  - `recurrence` *(string, optional, default: `"none"`)*: Recurrence frequency (`"none"`, `"daily"`, `"weekdays"`, `"weekly"`).
* **Structured Response:**
  ```json
  {
    "status": "scheduled",
    "task_id": "pt-8a12b3c4",
    "title": "unplug clothes iron",
    "domain": "safety",
    "scheduled_time": "08:30",
    "recurrence": "daily",
    "tracking_status": "watching_ambient_stream"
  }
  ```
* **Alexa Spoken Response:** *"I have scheduled your daily safety check to unplug the clothes iron at 08:30. I will monitor your ambient speech and check it off automatically once you do it."*

---

### 2. `verify_action_status` (Peace of Mind)
Instantly verifies whether a domestic safety action or routine task has been executed.
* **Tool Description:** *"Check the completion status and timestamp of a domestic safety action (e.g., iron, stove, front door, medication) or work task."*
* **Input Parameters:**
  - `action_query` *(string, required)*: Action keyword to verify (e.g. `"iron"`, `"stove"`, `"door"`, `"keys"`).
  - `target_date` *(string, optional)*: Reference date in `YYYY-MM-DD` format (default: today).
* **Structured Response:**
  ```json
  {
    "status": "verified",
    "action_type": "iron_unplugged",
    "timestamp": "2026-09-28T08:14:22+02:00",
    "raw_statement": "I'm unplugging the clothes iron before leaving",
    "confidence": 0.96,
    "elapsed_time_human": "3 hours and 12 minutes ago",
    "matched_task_id": "pt-8a12b3c4",
    "ui_card_type": "ACTION_VERIFIED_BADGE"
  }
  ```
* **Alexa Spoken Response:** *"Yes, you confirmed unplugging the iron this morning at 08:14, about 3 hours ago."*

---

### 3. `get_daily_actions_recap` (Daily Checklist & Log)
Returns a dual report of scheduled routines (completed vs pending vs overdue) and spontaneous actions discovered throughout the day.
* **Tool Description:** *"Retrieve the daily checklist of planned routines and chronological timeline of spontaneous ambient actions."*
* **Input Parameters:**
  - `domain` *(string, optional)*: Filter category (`"all"`, `"safety"`, `"routine"`, `"work_task"`).
  - `limit` *(integer, optional, default: 10)*.
* **Structured Response:**
  ```json
  {
    "date": "2026-09-28",
    "summary": {
      "planned_completed": 2,
      "planned_pending": 1,
      "spontaneous_actions": 2
    },
    "planned_routines": [
      {
        "id": "pt-8a12b3c4",
        "title": "Unplug clothes iron",
        "scheduled_time": "08:30",
        "status": "completed",
        "completed_at": "08:14",
        "verified_by_audio": true
      },
      {
        "id": "pt-9c44d1e2",
        "title": "Lock front door",
        "scheduled_time": "08:30",
        "status": "completed",
        "completed_at": "08:16",
        "verified_by_audio": true
      },
      {
        "id": "pt-3f88a9b0",
        "title": "Evening blood pressure medication",
        "scheduled_time": "21:00",
        "status": "pending",
        "completed_at": null,
        "verified_by_audio": false
      }
    ],
    "spontaneous_actions": [
      {"time": "11:30", "action": "Merged PR #42 on backend repo", "type": "work_task"},
      {"time": "14:15", "action": "Sent proposal email to client", "type": "work_task"}
    ]
  }
  ```
* **Alexa Spoken Response:** *"Today you completed 2 scheduled routines: unplugging the iron at 08:14 and locking the front door at 08:16. You still have 1 pending routine: evening medication at 21:00. You also recorded 2 work tasks."*

---

### 3. `query_social_contact` (Social Recall)
Recalls information on people met, corporate affiliations, and promises made.
* **Tool Description:** *"Search the social interactions registry for contacts by name, company, or discussed topics."*
* **Input Parameters:**
  - `name_or_query` *(string, required)*: Person's name or keyword (e.g. `"Marco"`, `"Stripe"`, `"startup"`).
* **Structured Response:**
  ```json
  {
    "found": true,
    "contact": {
      "name": "Marco Rossi",
      "company_or_role": "Tech Lead @ Acme Corp",
      "first_met": "2026-09-28T10:30:00+02:00",
      "key_topics": ["AWS Bedrock", "Agentic Architecture", "Seed Round"],
      "commitments": [
        "Send link to EXAMEN technical documentation",
        "Marco will send architectural feedback by Friday"
      ]
    },
    "ui_card_type": "SOCIAL_PROFILE_CARD"
  }
  ```
* **Alexa Spoken Response:** *"Marco Rossi is Tech Lead at Acme Corp. You discussed AWS Bedrock and promised to send him the EXAMEN documentation."*

---

### 4. `get_topic_briefing` (Deep Meeting & Lecture Intelligence)
Fetches the autonomous briefing report generated following a meeting or academic lecture.
* **Tool Description:** *"Retrieve executive technical briefing reports enriched with autonomous web research on discussed technologies, bugs, or study topics."*
* **Input Parameters:**
  - `topic_query` *(string, optional)*: Subject title or keyword (e.g. `"AgentCore"`, `"memory leak"`, `"turing machines"`). If omitted, returns the latest generated briefing.
* **Structured Response:**
  ```json
  {
    "topic_title": "AgentCore & AWS Bedrock Multi-Agent Orchestration",
    "context_type": "tech_stack",
    "created_at": "2026-09-28T12:05:00+02:00",
    "executive_summary": [
      "AgentCore manages resilient serverless agent runtimes with native Bedrock support.",
      "Handles state persistence and asynchronous tool invocations.",
      "Resolves concurrency issues discussed in the 11:00 AM engineering review."
    ],
    "web_sources": [
      "https://docs.aws.amazon.com/bedrock/latest/userguide/agents.html",
      "https://github.com/awslabs/amazon-bedrock-agentcore"
    ],
    "action_items": [
      "Update deployment harness on staging branch",
      "Configure IAM Policy bedrock:InvokeModel"
    ],
    "ui_card_type": "DEEP_BRIEFING_VIEWER"
  }
  ```

---

## 🖥️ Echo Show Visual Interface (`ext-apps` Iframe SDK)

Alexa+ supports the **`ext-apps`** extension, enabling the MCP server to project an interactive web application on touch-enabled **Echo Show (8, 10, 15)** devices.

### Wireframe Layout (Modern Dark UI)

```
┌────────────────────────────────────────────────────────────────────────┐
│ 🐝 EXAMEN Ambient OS                           📅 Monday, Sep 28       │
├───────────────────┬────────────────────────────────────────────────────┤
│ 🔒 Peace of Mind  │ 🟢 LATEST VERIFIED: Clothes Iron                   │
│ 📋 Daily Routines │ Time: 08:14:22 CEST (3 hours ago)                  │
│ 🧠 Social Rolodex │ Statement: "I'm unplugging the iron before leaving"│
│ 📚 Deep Briefings │ Auto-Resolved Task: [pt-8a12b3c4] Unplug iron      │
├───────────────────┴────────────────────────────────────────────────────┤
│ 📋 SCHEDULED ROUTINES & DOMESTIC SAFETY CHECKLIST:                     │
│ [✓] 08:14 - Unplug clothes iron (Scheduled: 08:30) [Verified by audio] │
│ [✓] 08:16 - Lock front door (Scheduled: 08:30)     [Verified by audio] │
│ [⏳] 21:00 - Evening blood pressure medication     [PENDING]           │
├────────────────────────────────────────────────────────────────────────┤
│ ⚡ SPONTANEOUS AMBIENT ACTIONS DISCOVERED:                              │
│ [✓] 11:30 - Deployed staging build (PR #42)                            │
│ [✓] 14:15 - Sent proposal email to client                              │
└────────────────────────────────────────────────────────────────────────┘
```

### Visual Card 2: Deep Topic Briefing Card

```
┌────────────────────────────────────────────────────────────────────────┐
│ 📚 Deep Tech Briefing: AWS AgentCore Architecture                      │
├────────────────────────────────────────────────────────────────────────┤
│ 💡 Executive Summary:                                                  │
│ • Serverless scalable agent runtime environment.                       │
│ • Native integration with Claude 3.5 Haiku (routing) and Sonnet.       │
│                                                                        │
│ 🌐 Autonomously Consulted Sources:                                     │
│ • AWS Bedrock Agents Developer Guide [🔗 docs.aws.amazon.com]          │
│ • GitHub: awslabs/bedrock-agentcore [🔗 github.com]                    │
│                                                                        │
│ 📌 Meeting Action Items:                                               │
│ [ ] Configure IAM Role with least-privilege invocation permissions     │
│ [ ] Test gatekeeper latency on 30-second sliding window                │
│                                                                        │
│ [ Email to Me ✉️ ]    [ Share to Slack 💬 ]                            │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🔌 `addon.json` Configuration for Alexa+ CLI

To register the MCP Server within the Alexa+ developer preview:

```json
{
  "name": "examen-mcp",
  "version": "1.0.0",
  "description": "Ambient intelligence and memory augmentation server for Bee wearable and Echo Show",
  "mcp": {
    "server": {
      "transport": "http",
      "url": "https://examen-tunnel.yourdomain.com/mcp",
      "capabilities": {
        "tools": true,
        "resources": true,
        "prompts": true
      }
    }
  },
  "extApps": {
    "entryPoint": "https://examen-tunnel.yourdomain.com/ext-app/index.html",
    "displayModes": ["full_screen", "card_modal"]
  }
}
```
