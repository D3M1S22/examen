# 🏆 Hackathon Strategy, Pitch & Demo Video Script

> This document outlines the **competition strategy** to maximize jury score in the **Amazon Developer Hackathon 2026**, detailing judging criteria alignment, the 3-minute video demo script, and the 4-sprint execution roadmap.

---

## 🎯 Judging Criteria Alignment & Competitive Edge

Judges for the **Bee Wearable AI** track and the **AWS Builder** mini-challenge look for specific differentiators between obvious concepts and winning architectures:

| Official Judging Criteria | Obvious / Common Idea | The EXAMEN Winning Response |
| :--- | :--- | :--- |
| **Cross-Device Orchestration** | Basic notification forwarded from smartwatch to phone. | **Bee Wearable + Echo Show (Alexa+):** Ambient passive capture on the go (Bee); multimodal voice and touch retrieval at home/office (Echo Show). |
| **Ambient Context Capture** | Awkward wake-words required (*"Hey Bee, remember this..."*). | **Zero-shot ambient processing:** User speaks naturally. The semantic gatekeeper on Bedrock isolates signal without any forced activation phrase. |
| **Advanced Facts & Insights** | Chronological list of raw audio transcripts. | **Autonomous Enrichment:** When complex topics or technical discussions arise, EXAMEN executes background web research and synthesizes an executive briefing. |
| **AWS Builder Challenge ($5,000 + $5,000 credits)** | Generic API calls to a single third-party model. | Deep, structured utilization of **AWS Bedrock** with multi-model tiering (Haiku for screening, Sonnet for synthesis) and **AgentCore Runtime**. |

---

## 💰 Target Prize Pool

* 🥇 **1st Place Bee Wearable AI Track:** **$12,000 cash**
* ⚡ **Winner AWS Builder Mini-Challenge:** **$5,000 cash + $5,000 AWS credits**
* 🎁 **Bonus Opportunity:** 1:1 Executive Mentorship with Amazon Alexa & AWS Senior Leadership.
* **Total Potential:** **$17,000 cash + $5,000 AWS credits**.

---

## 🎬 3-Minute Video Demo Script & Storyboard

> **Golden Rule:** A winning hackathon video frames the friction in the first 30 seconds, demonstrates the tech under the hood in the middle minute, and showcases 3 indisputable practical scenarios.

```
0:00 ─── 0:35 ─── 1:15 ─── 1:50 ─── 2:25 ─── 3:00
  [Problem]     [Architecture]   [Scene 1: Social]  [Scene 2: Deep Tech]  [Scene 3: Peace of Mind]  [Stack Recap]
```

### [0:00 - 0:35] Intro: Daily Cognitive Overload
* **Visual:** Fast-paced montage. User leaves home in a rush, muttering: *"Iron unplugged, front door locked"*.
* Arrives at a tech coworking space; someone introduces themselves: *"Hey, I'm Dario, Tech Lead at CloudScale, make sure to send me your project docs tomorrow!"*.
* Enters an engineering sync: the team debates a new framework (*"We need to evaluate AWS AgentCore and investigate that library memory leak"*).
* **Voiceover:** *"Every day, our minds are bombarded by hundreds of fleeting micro-interactions: promised follow-ups, nagging home anxieties, and technical topics we don't have time to research. Traditional voice assistants force you to stop and type. Meet EXAMEN."*

### [0:35 - 1:15] Behind the Scenes: Bee, Bedrock & AgentCore
* **Visual:** Close-up of the Bee wearable lapel microphone. Developer screen showing real-time `bee-cli` SSE stream.
* On-screen pipeline telemetry:
  1. *Gatekeeper (Claude 3.5 Haiku):* Filters out 95% of background chatter at zero cost.
  2. *Routing:* Dispatches qualified speech across Social, Action-State, and Deep Topic channels.
* **Voiceover:** *"Powered by Bee's continuous audio stream, EXAMEN (Latin for 'swarm of bees' and 'careful examination') leverages AWS Bedrock with an ultra-efficient semantic gatekeeper. It identifies genuine signal, triggers the AgentCore state graph, and enriches data autonomously."*

### [1:15 - 1:50] Scene 1: Social Recall (Relational Memory)
* **Visual:** User runs into Dario 40 minutes later by the coffee machine. Glances at smartwatch/phone for 2 seconds.
* Notification card: *"Dario - Tech Lead @ CloudScale | To-do: Send project documentation"*.
* User greets him by name without hesitation: *"Hey Dario! I'll send that repo over this afternoon"*.
* **Voiceover:** *"Never again face the awkwardness of forgetting a name or a promise you just made."*

### [1:50 - 2:25] Scene 2: Deep Meeting Intelligence on Echo Show
* **Visual:** Meeting ends; user returns to desk in front of an **Echo Show 10/15**.
* User: *"Alexa, show me the briefing on the technologies discussed in this morning's meeting."*
* Alexa responds: *"I prepared an executive briefing on AWS AgentCore with official docs and two team action items."*
* Via **ext-apps**, an elegant interactive dark-mode dashboard appears on screen displaying summaries, links, and checklist items.
* **Voiceover:** *"Instead of scrambled notes, EXAMEN detected key topics, researched official docs, and prepared an executive dossier ready for action."*

### [2:25 - 2:50] Scene 3: Action-State & Daily Peace of Mind
* **Visual:** User is at their desk and gets struck by familiar anxiety: *"Wait, did I unplug the iron before leaving?"*.
* Asks Alexa: *"Alexa, did I unplug the clothes iron?"*.
* Alexa responds: *"Yes, at 08:14 you confirmed unplugging the iron before leaving."*
* A certified green badge appears on the Echo Show screen with the exact utterance and timestamp.
* **Voiceover:** *"Zero anxiety, zero lost time. Certified actions with exact timestamps."*

### [2:50 - 3:00] Conclusion & Stack Recap
* **Visual:** Summary slide with partner logos: **Bee Wearable AI + AWS Bedrock + AgentCore + Alexa+ MCP**.
* **Voiceover:** *"EXAMEN transforms ambient listening into your augmented second brain. Built for AWS Bedrock and Alexa+."*

---

## 📅 4-Sprint Development Roadmap

```
Sprint 1 (Ingestion & Gatekeeper)
├── Configure Bee CLI environment & test SSE live stream with bee-cli
├── Request AWS credits & configure Bedrock models (Haiku & Sonnet)
└── Calibrate Gatekeeper prompt for >90% drop rate on irrelevant chit-chat

Sprint 2 (AgentCore Harness & Deep Research)
├── Build LangGraph / AgentCore state graph with 3 specialized nodes
├── Integrate autonomous Web Search tooling for Deep Topic channel
└── Implement local SQLite context store with full-text search (FTS5)

Sprint 3 (Alexa+ MCP Server & Ext-Apps UI)
├── Implement FastMCP streamable-HTTP server exposing 4 core tools
├── Test local voice interaction via Alexa+ CLI and Cloudflare Tunnel
└── Develop interactive touch UI for Echo Show via ext-apps iframe SDK

Sprint 4 (Polishing, Video Demo & Submission)
├── Conduct end-to-end integration test of video demo scenario
├── Record and produce 3-minute 1080p demo video (clean audio & subtitles)
├── Finalize GitHub documentation and Devpost submission narrative
└── Submit before official hackathon deadline
```

---

## 📝 Friction Log Rule (+10% Bonus Points)

Hackathon guidelines reward a **+10% bonus score** for teams maintaining a transparent developer diary (*Friction Log*) detailing platform issues, SDK bugs, and workarounds.

Throughout development, log all events in [FRICTION_LOG.md](../FRICTION_LOG.md).
