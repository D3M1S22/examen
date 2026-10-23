# 🎬 EXAMEN — 3-Minute Video Pitch Script & Production Guide

> **Document Status:** Official Production Guide & Pitch Storyboard  
> **Language:** English (Audio Voiceover, On-screen Text, UI Mockups)  
> **Target Duration:** 3:00 Max (180 seconds / 5,310 frames @ 30 fps)  
> **Resolution & Format:** 1920×1080 (1080p, 30/60 fps, 16:9)  
> **Live Demo Target:** [`https://examen.devgiov.com`](https://examen.devgiov.com)  
> **Remotion Project Directory:** [`video-pitch/`](../video-pitch/)  
> **Hackathon Submission Tracks:** Bee Wearable AI, AWS Builder Mini-Challenge, Alexa+ Track  

---

## 🧭 Executive Summary & Timing Map

This video pitch is crafted for the **Amazon Developer Hackathon 2026** jury. It alternates between **high-impact animated graphics** (framing the problem, AWS cloud architecture, FastMCP protocol, and closing impact) and **real screen recordings** of the production Next.js 14 Web UI running live at `https://examen.devgiov.com`.

```
0:00 ────── 0:30 ────── 1:00 ────── 1:35 ────── 2:05 ────── 2:30 ────── 2:45 ────── 3:00
[ Problem ]     [ Cloud Architecture ] [ Deep Topics ]   [ Social Rolodex ]   [ Peace of Mind ]  [ Alexa+ MCP ]  [ Closing ]
 (Motion GFX)      (Diagram Slide)      (Live UI Screen)   (Live UI Screen)    (Live UI Screen)   (Slide + UI)   (Final Slide)
```

| Interval | Duration | Format | Narrative Section | Word Count (~135 wpm) |
| :--- | :--- | :--- | :--- | :--- |
| **0:00 – 0:30** | 30s | Motion Graphic / Cards | The Friction & The EXAMEN Vision | ~65 words |
| **0:30 – 1:00** | 30s | Architecture Flow Diagram | Bee Hardware & AWS Bedrock Gatekeeper | ~70 words |
| **1:00 – 1:35** | 35s | Live Screen Recording | Deep Topic Event Engine & Echo Show View | ~80 words |
| **1:35 – 2:05** | 30s | Live Screen Recording | Social Rolodex & Bilateral Commitments | ~70 words |
| **2:05 – 2:30** | 25s | Live Screen Recording | Peace of Mind & Speaker Verification | ~55 words |
| **2:30 – 2:45** | 15s | Slide + Live API Call | Alexa+ FastMCP Server on AWS (22 tools) | ~35 words |
| **2:45 – 3:00** | 15s | Final Metric Slide | Metrics, Hackathon Alignment & Impact | ~35 words |
| **Total** | **180s (3:00)** | **Hybrid Slide / Live UI** | **Complete Pitch** | **~410 words** |

---

## 📜 Complete English Storyboard & Turn-by-Turn Script

### 1. The Problem & The Vision [0:00 – 0:30]
* **Visuals (Motion Graphics):**
  - **[0:00–0:12]:** Deep slate canvas (`#080C14`). Three floating cards animate into view, visualizing everyday cognitive overload:
    - Card 1: *"What did I promise Marco?"* (Lost verbal commitments)
    - Card 2: *"What was the sync architecture?"* (Forgotten technical meeting details)
    - Card 3: *"Did I unplug the clothes iron?"* (Nagging domestic anxiety)
  - **[0:12–0:20]:** Legacy voice AI limitation card:
    - Traditional assistants are passive, reactive, and dependent on awkward wake-words.
  - **[0:20–0:30]:** Fluid transition to the **EXAMEN** brand reveal:
    - Logo: Glowing amber bee icon with bold typography `EXAMEN`.
    - Tagline: `Ambient Executive Intelligence`.
    - Partner Badges: `Bee Wearable AI × AWS Bedrock × Alexa+ MCP`.
* **On-Screen Lower Thirds:**
  - `Zero Wake-Words` · `Zero Cognitive Load` · `Continuous Ambient Intelligence`
* **Voiceover Script (English):**
  > *"Every day, our minds are bombarded by hundreds of fleeting verbal interactions: promises made on the fly, complex technical details, and constant anxiety over everyday tasks.*  
  > *Traditional voice assistants are passive and reactive: they always require an awkward wake-word and break our natural workflow.*  
  > *Introducing **EXAMEN**: our executive second brain that listens in the background, filters out the noise, and organizes our life in real time."*

---

### 2. Behind the Scenes: Bee Hardware & AWS Cloud [0:30 – 1:00]
* **Visuals (Animated Architecture Flow Diagram):**
  - **[0:30–0:42]:** Render of the open-source **Bee Wearable AI** badge emitting a continuous Server-Sent Events audio stream (`bee stream --json`).
  - **[0:42–1:00]:** Zoom-in on the 4-stage pipeline diagram:
    - **Stage 1 (Hardware Ingestion):** Continuous microphone capture on Bee.
    - **Stage 2 (Semantic Gatekeeper):** Ultra-fast **AWS Bedrock** model (Amazon Nova Micro) dropping **>90% of casual chatter** at sub-cent daily cost (<$0.01/day).
    - **Stage 3 (AgentCore Orchestration):** Qualified signals route into the LangGraph state graph powered by **AWS Bedrock AgentCore** (Claude 3.5 Sonnet).
    - **Stage 4 (Cloud Storage):** Multi-table tenant isolation on **Amazon DynamoDB** (`examen-user`, `examen-auth`, `examen-ops`) in `eu-central-1`.
* **On-Screen Lower Thirds:**
  - `Bee Wearable SSE Stream` ➔ `Bedrock Gatekeeper (>90% noise filtered)` ➔ `AgentCore Pipeline` ➔ `DynamoDB Multi-tenant`
* **Voiceover Script (English):**
  > *"EXAMEN captures continuous ambient audio directly from the open-source Bee wearable pendant.*  
  > *At its heart lies the Semantic Gatekeeper on AWS Bedrock: an ultra-lightweight model drops over 90% of casual chatter with near-zero latency and sub-cent daily cost.*  
  > *The moment it detects genuine executive signal—a promise, a physical action, or a technical topic—it routes context to LangGraph on AWS Bedrock AgentCore and synchronizes with Amazon DynamoDB."*

---

### 3. Live Demo 1: Deep Topic Event Engine & Echo Show View [1:00 – 1:35]
* **Visuals (Screen Recording of `https://examen.devgiov.com`):**
  - **[1:00–1:15]:** Browser view in fullscreen dark mode. Navigation to **Topic Dossiers**. The user selects the active dossier: *"AWS Bedrock AgentCore & LangGraph Architecture"*.
  - **[1:15–1:25]:** Inspection of the executive briefing: chapters, key takeaways, and the **Web Sources** section showing attached official documentation retrieved via autonomous background web search.
  - **[1:25–1:35]:** Clicking the **Echo Show View** button: the `EchoShowModal` slides in, showcasing the interactive touch UI card formatted for smart displays like Echo Show 10 or 15.
* **On-Screen Lower Thirds:**
  - `Deep Topic Event Engine` · `Autonomous Web Research & Grounding` · `Echo Show Touch Experience`
* **Voiceover Script (English):**
  > *"Let's see it in action on our live AWS cloud deployment.*  
  > *During a sync meeting, the Event Engine detects technical discussions, generates an executive dossier organized into chapters, and performs autonomous web research to attach official documentation.*  
  > *The dossier is accessible both on the web dashboard and through this interactive touch view, formatted natively for Alexa Echo Show smart displays."*

---

### 4. Live Demo 2: Social Rolodex & Bilateral Promises [1:35 – 2:05]
* **Visuals (Screen Recording of `https://examen.devgiov.com`):**
  - **[1:35–1:50]:** Clicking the **Social Rolodex** tab. Viewing contact card *"Dario – Tech Lead @ CloudScale"*. Highlighting the **Bilateral Commitments** block:
    - *"I owe Dario: Send repository documentation by 5 PM"* (Debtor: User).
    - *"Dario owes me: Architecture review"* (Creditor: User).
  - **[1:50–2:05]:** Quick navigation to **Daily Routines**: showing that the commitment has been automatically scheduled as an actionable task with confidence score and due time.
* **On-Screen Lower Thirds:**
  - `Relational Memory` · `Bilateral Commitments (Debtor / Creditor)` · `Ambient Task Extraction`
* **Voiceover Script (English):**
  > *"On the relational front, the Social Rolodex tracks people and bilateral promises.*  
  > *If you tell a colleague 'I will send you the repo docs by 5 PM', EXAMEN understands debtor and creditor roles, resolves deadlines, and automatically provisions an actionable task in your daily routines, without touching the keyboard."*

---

### 5. Live Demo 3: Peace of Mind & Speaker Verification [2:05 – 2:30]
* **Visuals (Screen Recording of `https://examen.devgiov.com`):**
  - **[2:05–2:18]:** Clicking the **Peace of Mind** tab. Highlighting verified physical action states:
    - *"Clothes Iron Unplugged — Confirmed today at 08:14:22 (Verbatim: 'Iron unplugged, heading out')"*.
    - *"Front Door Locked — Confirmed today at 08:16:05"*.
  - **[2:18–2:30]:** Opening the **Speaker Review** drawer: showing how an unverified audio snippet is queued for 1-click user confirmation (`Accept` or `Dismiss`), ensuring privacy and data provenance.
* **On-Screen Lower Thirds:**
  - `Certified Action-State Verification` · `Tamper-evident Timestamps` · `Speaker Review & Privacy Guardrails`
* **Voiceover Script (English):**
  > *"For everyday peace of mind, the verified action-state engine certifies physical tasks with exact timestamps and verbatim transcripts, eliminating domestic anxiety.*  
  > *And to guarantee privacy and precision, the Speaker Review drawer allows you to inspect and confirm untagged speech with a single click."*

---

### 6. Alexa+ Track: FastMCP Server on AWS [2:30 – 2:45]
* **Visuals (Diagram Slide + Live Endpoint Preview):**
  - **[2:30–2:38]:** Diagram showing the **FastMCP Protocol (2025-11-25)** live on AWS:
    - Endpoint: `https://examen.devgiov.com/mcp` over Streamable HTTP.
    - 4 Clusters of **22 Production Tools** (Certified Actions, Deep Topics, Commitments, Speaker Review).
  - **[2:38–2:45]:** Echo device voice conversation simulation:
    - User: *"Alexa, what commitments did I make today?"*
    - Alexa: *"You have 1 commitment with Dario: send him the project documentation by 5:00 PM."*
* **On-Screen Lower Thirds:**
  - `FastMCP Protocol (2025-11-25)` · `22 Production MCP Tools` · `Live Streamable HTTP on AWS`
* **Voiceover Script (English):**
  > *"For the Alexa+ track, EXAMEN serves a compliant FastMCP server with 22 tools over Streamable HTTP, already live on AWS.*  
  > *Alexa+ can naturally query your commitments, certified actions, and executive briefings directly from any Echo device at home or the office."*

---

### 7. Conclusion, Impact & Hackathon Summary [2:45 – 3:00]
* **Visuals (Final Showcase Slide):**
  - Premium dark backdrop with glowing bee icon.
  - 4 Key Metric Pillars:
    - `588 Automated Tests (100% Green)`
    - `< $0.01 Daily Operational Cost (Nova Micro Gatekeeper)`
    - `22 Live FastMCP Tools on AWS`
    - `Multi-tenant Isolation on Amazon DynamoDB`
  - Technology partner logos: **Bee Wearable AI** · **AWS Bedrock & AgentCore** · **Amazon DynamoDB** · **Alexa+**
* **On-Screen Lower Thirds:**
  - `EXAMEN — Ambient Executive Intelligence` · `Amazon Developer Hackathon 2026`
* **Voiceover Script (English):**
  > *"With over 580 automated tests and a scalable, ultra-low-cost cloud architecture, EXAMEN turns ambient listening into your most reliable executive partner.*  
  > *EXAMEN: augmented memory for everyday life. Thank you!"*

---

## 🛠️ Practical Production Steps with Remotion

### 1. Previewing in Remotion Studio
```bash
cd video-pitch
npm run dev
```
Open `http://localhost:3000` to review the entire video or each individual scene.

### 2. Dropping In Your Own Screen Recordings
Whenever you record a video clip from `https://examen.devgiov.com`:
1. Save it to `video-pitch/public/recordings/` (e.g. `topics.mp4`, `social.mp4`, `peace.mp4`).
2. Replace or embed the video inside the corresponding scene using Remotion's `<Video src={staticFile("recordings/topics.mp4")} />`.
3. By default, high-fidelity animated UI mockups are already built into every scene.

### 3. Voiceover & Audio Recording
- Record the voiceover using the verbatim English script above (~410 words).
- Save the audio file as `video-pitch/public/voiceover.mp3`.
- In `src/ExamenPitchVideo.tsx`, you can mount:
  ```tsx
  <Audio src={staticFile("voiceover.mp3")} volume={1} />
  ```
- Add background instrumental music at `video-pitch/public/bg_music.mp3` with `volume={0.12}`.

### 4. Exporting the Final Video
```bash
cd video-pitch
npm run render
```
The output file is generated at `video-pitch/out/examen-pitch.mp4` (1080p Full HD, 30 fps, H.264, ~2m 57s).
