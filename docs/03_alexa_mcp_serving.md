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

### 1. `verify_action_status` (Peace of Mind)
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
    "ui_card_type": "ACTION_VERIFIED_BADGE"
  }
  ```
* **Alexa Spoken Response:** *"Yes, you confirmed unplugging the iron this morning at 08:14, about 3 hours ago."*

---

### 2. `get_daily_actions_recap` (Daily Log & Standup)
Returns an ordered chronological timeline of verified actions and work tasks completed throughout the day.
* **Tool Description:** *"Retrieve the chronological timeline of routine actions completed and work tasks performed."*
* **Input Parameters:**
  - `domain` *(string, optional)*: Filter category (`"all"`, `"safety"`, `"work_task"`).
  - `limit` *(integer, optional, default: 10)*.
* **Structured Response:**
  ```json
  {
    "date": "2026-09-28",
    "total_actions": 4,
    "items": [
      {"time": "08:14", "action": "Unplugged clothes iron", "type": "safety"},
      {"time": "08:16", "action": "Locked front door", "type": "safety"},
      {"time": "11:30", "action": "Merged PR #42 on backend repo", "type": "work_task"},
      {"time": "14:15", "action": "Sent proposal email to client", "type": "work_task"}
    ]
  }
  ```

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
│ 🔒 Peace of Mind  │ 🟢 VERIFIED: Clothes Iron                          │
│ 🧠 Social Rolodex │ Time: 08:14:22 CEST (3 hours ago)                  │
│ 📚 Deep Briefings │ Verified statement:                                │
│                   │ "I'm unplugging the clothes iron before leaving"   │
│                   │ Confidence: 96%  |  Sensor: Bee Wearable Lapel     │
├───────────────────┴────────────────────────────────────────────────────┤
│ 📋 RECENT VERIFIED ACTIONS:                                            │
│ [✓] 08:16 - Front door locked                                          │
│ [✓] 11:30 - Deployed staging build (PR #42)                             │
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
