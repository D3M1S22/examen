# 🎬 19 — Video Pitch v2: Script, Live Demo and Voiceover Timing

> **Status:** v2 draft, built on 2026-10-23 next to v1 (nothing in v1 changed).
> **v1 (kept as is):** [18_video_pitch_script_and_production_guide.md](18_video_pitch_script_and_production_guide.md), composition `ExamenPitchVideo`.
> **v2:** this document, composition `ExamenPitchVideoV2` in [`video-pitch/src/v2/`](../video-pitch/src/v2/).
> **Length:** **2:54.5** (5,235 frames @ 30 fps, 1920×1080). Under the hackathon's 3-minute limit with 5.5 s to spare ([14](14_aws_and_hackathon_reference.md)).
> **Single source of truth for timing:** [`video-pitch/src/v2/voiceover-v2.json`](../video-pitch/src/v2/voiceover-v2.json). The subtitles, the audio placeholders, the teleprompter overlay and the tables below all come from it.

---

## 1. What changes from v1

| | v1 | v2 |
|---|---|---|
| Storyboard | 7 scenes, 3:00 slot (2:57 rendered) | Same 7 scenes in shorter slots, **plus a live example as scene 03** |
| Live moment | None (mockups only) | You say *"Remind me to contact Danilo and coordinate about the hackathon submission"*; it appears in Daily Routines |
| Alexa+ scene | Asks about commitments with Dario | Asks *"what's on my plate today?"*; the answer includes Danilo (pays off the live moment). Tool names now match the real 22 MCP tools |
| Audio | None | One audio clip per line on the timeline (silent placeholders until recorded) + a silent music bed |
| Subtitles | Hard-coded in each scene | Generated from the voiceover JSON |
| VO script | Paragraphs per scene | **Line by line, with start, end and length** |
| Teleprompter | None | `ExamenPitchVideoV2-Guide` composition shows the current line, a countdown and the next line |

The v1 scenes were copied to `src/v2/scenes/` and play their same animation beats faster (×1.17–1.25) to fit the shorter slots; the copies have no built-in subtitles.

---

## 2. Scene slots

Each scene overlaps the next by a 0.5 s crossfade, so a scene starts 0.5 s before the previous one ends.

| Scene | Slot | Starts | Ends |
|---|---|---|---|
| 01 Vision & Problem | 24 s | 0:00.0 | 0:24.0 |
| 02 Bee + AWS Architecture | 24 s | 0:23.5 | 0:47.5 |
| **03 LIVE: Remind me about Danilo** (new) | 26 s | 0:47.0 | 1:13.0 |
| 04 Deep Topic Event Engine | 30 s | 1:12.5 | 1:42.5 |
| 05 Social Rolodex | 24 s | 1:42.0 | 2:06.0 |
| 06 Peace of Mind | 20 s | 2:05.5 | 2:25.5 |
| 07 Alexa+ MCP | 15 s | 2:25.0 | 2:40.0 |
| 08 Closing | 15 s | 2:39.5 | 2:54.5 |

---

## 3. Voiceover script with timing (record these lines)

Times are absolute positions in the final video. **Length** is the time the line has (planned at 2.5 words per second, about 150 wpm, plus a short breath). A take may run a little longer, up to the start of the next line, without being cut. **YOU, LIVE** is the sentence you speak on camera to the Bee, not studio voiceover.

| # | Who | Starts | Ends | Length | Words | Line | File |
|---|---|---|---|---|---|---|---|
| 1.1 | VO | 0:00.6 | 0:07.8 | **7.2 s** | 17 | Every day, our minds juggle fleeting conversations: promises made on the fly, technical details, small nagging worries. | `vo_1_1.wav` |
| 1.2 | VO | 0:08.2 | 0:15.0 | **6.8 s** | 16 | Traditional voice assistants are passive: they wait for a wake word and break our natural flow. | `vo_1_2.wav` |
| 1.3 | VO | 0:16.0 | 0:23.2 | **7.2 s** | 17 | Introducing EXAMEN: a second brain that listens in the background, filters the noise, and organizes your day. | `vo_1_3.wav` |
| 2.1 | VO | 0:24.1 | 0:29.8 | **5.7 s** | 13 | EXAMEN listens through the open-source Bee wearable, streaming every utterance in real time. | `vo_2_1.wav` |
| 2.2 | VO | 0:31.5 | 0:38.7 | **7.2 s** | 17 | On AWS Bedrock, a Semantic Gatekeeper drops over ninety percent of chatter, for just cents a day. | `vo_2_2.wav` |
| 2.3 | VO | 0:39.5 | 0:46.7 | **7.2 s** | 17 | Real signal, like a promise or a technical topic, goes to LangGraph on AgentCore and into DynamoDB. | `vo_2_3.wav` |
| 3.1 | VO | 0:47.6 | 0:52.0 | **4.4 s** | 10 | Let's try it live. No wake word. I just say: | `vo_3_1.wav` |
| 3.2 | **YOU, LIVE** | 0:52.0 | 0:57.0 | **5.0 s** | 11 | Remind me to contact Danilo and coordinate about the hackathon submission. | `live_3_2.wav` |
| 3.3 | VO | 0:57.4 | 1:06.2 | **8.8 s** | 21 | Bee streams it, the Gatekeeper tags it as a task, and the scheduler files it in Daily Routines, linked to Danilo. | `vo_3_3.wav` |
| 3.4 | VO | 1:06.8 | 1:11.7 | **4.9 s** | 11 | No typing, no follow-up. It's already there when I need it. | `vo_3_4.wav` |
| 4.1 | VO | 1:13.1 | 1:19.9 | **6.8 s** | 16 | In meetings, the Event Engine spots technical discussions and builds an executive dossier, organized into chapters. | `vo_4_1.wav` |
| 4.2 | VO | 1:22.5 | 1:30.9 | **8.4 s** | 20 | It runs web research in the background and attaches the official documentation it finds, so every claim has a source. | `vo_4_2.wav` |
| 4.3 | VO | 1:33.5 | 1:39.9 | **6.4 s** | 15 | And the same dossier opens as a touch view, built for Alexa Echo Show displays. | `vo_4_3.wav` |
| 5.1 | VO | 1:42.6 | 1:51.0 | **8.4 s** | 20 | The Social Rolodex remembers people and the promises between you, in both directions: what you owe, and what you're owed. | `vo_5_1.wav` |
| 5.2 | VO | 1:53.0 | 2:04.3 | **11.3 s** | 27 | Say 'I'll send you the repo docs by 5 PM', and EXAMEN works out who owes what, sets the deadline, and adds the task to your day. | `vo_5_2.wav` |
| 6.1 | VO | 2:06.1 | 2:13.3 | **7.2 s** | 17 | For peace of mind, EXAMEN certifies physical actions with exact timestamps and the words you actually said. | `vo_6_1.wav` |
| 6.2 | VO | 2:16.1 | 2:23.3 | **7.2 s** | 17 | And when it isn't sure who spoke, the item waits in Speaker Review for your one-click confirmation. | `vo_6_2.wav` |
| 7.1 | VO | 2:25.6 | 2:32.0 | **6.4 s** | 15 | For Alexa+, EXAMEN runs an MCP server on AWS, with twenty-two tools over Streamable HTTP. | `vo_7_1.wav` |
| 7.2 | VO | 2:32.4 | 2:38.8 | **6.4 s** | 15 | So later I just ask Alexa what's on my plate, and Danilo is right there. | `vo_7_2.wav` |
| 8.1 | VO | 2:40.1 | 2:48.9 | **8.8 s** | 21 | With over 580 automated tests and an ultra-low-cost cloud architecture, EXAMEN turns ambient listening into a partner you can rely on. | `vo_8_1.wav` |
| 8.2 | VO | 2:49.5 | 2:53.1 | **3.6 s** | 8 | EXAMEN: augmented memory for everyday life. Thank you! | `vo_8_2.wav` |

**Totals:** 21 lines, 342 words (20 voiceover lines + 1 live line), about 2:20 of speech in 2:54.5 of video. The gaps are deliberate: they let the visuals land.

### Reading notes
- **Pace:** relaxed, about 150 words per minute. If a line runs long, cut words, not pauses.
- **1.3 / 8.2:** stress *EXAMEN* and pronounce it the same way every time.
- **3.1 → 3.2:** leave a real beat after "I just say:", then speak the live line naturally, as if talking to yourself.
- **3.2:** say **"Remind me to…"**, not "Remember me to…". The cloud Gatekeeper model understands both, but its offline fallback patterns only match *remind me to / remember to / don't forget to* (`src/ingestion/gatekeeper.py`), and "remind me to" is the natural English phrasing.
- **7.2:** the Alexa+ exchange is labelled on screen as a simulated conversation through `get_upcoming_tasks`, as the Alexa+ track rules require.

---

## 4. Storyboard of the new scene: 03 Live Demo (0:47.0 – 1:13.0)

| Time in scene | Picture | Audio |
|---|---|---|
| 0.0 – 5.0 s | Left: **● LIVE** badge, Bee pendant with idle listening rings. Right: four pipeline steps, dimmed | VO 3.1 |
| 5.0 – 10.0 s | Rings and waveform react; the sentence types out in the *YOU, OUT LOUD* bubble; the raw `bee stream --json` event appears | **LIVE 3.2** |
| 10.6 – 15.0 s | Steps tick one by one: Bee SSE stream → Semantic Gatekeeper (`scheduled_task · social`) → Scheduler node (`PlannedTask · work_task`) → DynamoDB `examen-user` + SSE push | VO 3.3 |
| 16.0 s | **Daily Routines · new task** card: *"Contact Danilo to coordinate the hackathon submission"*, tags WORK_TASK · PENDING · TODAY · 👤 Danilo; stat tiles *1 sentence · 0 taps · ~1 s screening* | VO 3.3 (continues) |
| 19.8 – 26.0 s | Banner: *"Said once. Captured, tracked, linked to Danilo. Zero taps."* | VO 3.4 |

The left panel is an animated mock by default. Once you have a real clip, set `liveClipSrc` (§6) and the clip plays in that panel instead.

### What happens in the code (so the scene stays honest)
1. Bee emits `new-utterance` on its SSE stream; EXAMEN waits up to `BEE_SPEAKER_TAG_WAIT_SECONDS` (1.5 s) for a `tagged-utterance` that binds it to the wearer (`src/ingestion/stream_convo.py`, `orchestrator.py`).
2. The Gatekeeper (`src/ingestion/gatekeeper.py`) labels it `scheduled_task`, and possibly `social` because a person is named.
3. The pipeline (`src/pipeline/graph.py`) runs the scheduler node (`nodes/scheduler.py`): a `PlannedTask` with domain `work_task`, `scheduled_time = null` (no time was given), recurrence `none`.
4. The store writes it (DynamoDB in production) and `broadcast_event` pushes an SSE event, so the **Daily Routines** view (`?tab=routines`) updates without a refresh.

---

## 5. Recording the live part for real (pre-flight checklist)

The Bee track asks to show the project running on the intended device, so a real capture is better than the mock.

1. **Speaker review.** If the Bee does not tag the utterance to you within 1.5 s, the task lands in **Speaker Review** (status `review`), not in Daily Routines. For the take, either turn on auto-accept of untagged speech in **Account** (`SPEAKER_AUTO_ACCEPT_UNTAGGED` in single-user mode), or leave it off and show yourself accepting the item from the Review tray (that also sets up scene 06).
2. **Bee paired and streaming:** the system bar shows `BEE: STREAMING`.
3. **Dashboard ready:** open `https://examen.devgiov.com/?tab=routines`, logged in, browser zoom set so the list is readable at 1080p, other tabs and bookmarks hidden.
4. **Clean slate:** delete earlier Danilo test tasks (two-step delete) so the new one stands out.
5. **Rehearse once** and note the real delay until the card appears. If it is long, cut the wait in editing; nothing in the voiceover promises a specific delay.
6. **Fallback:** if the device misbehaves, the Ambient Simulator tab can inject the same sentence. In that case label the clip *simulated input* so the video stays truthful.

### Screen-recording shot list (Cap or any recorder)
| Clip | File in `video-pitch/public/recordings-v2/` | What to capture | Raw length |
|---|---|---|---|
| A | `live_reminder.mp4` | You speaking the line (camera, or screen with mic), then Daily Routines receiving the task | 15–20 s |
| B | `topics.mp4` | Topic Dossiers → a dossier → Web Sources → **Echo Show View** | 30 s |
| C | `social.mp4` | Social Rolodex → contact card → commitments | 25 s |
| D | `peace.mp4` | Peace of Mind → verified actions → Speaker Review drawer | 20 s |

Only clip A is wired into v2 today (`liveClipSrc`). B–D can replace the mockups later, as v1's guide describes, with `<Video src={staticFile("recordings-v2/…")} />` from `@remotion/media`.

---

## 6. Working with the Remotion project

All commands run from `video-pitch/`. On this machine they run inside the Nix dev shell (`nix develop`, or automatically through direnv's `use flake`), which provides `bun` and `nodejs`.

```bash
cd video-pitch
npm run vo:placeholders      # silent WAVs for missing lines only (never overwrites a recorded take)
npm run dev                  # Remotion Studio → folder "v2" → ExamenPitchVideoV2
```

- **Timeline:** each line is a clip named like `VO 3.3 · 8.8s` or `LIVE 3.2 · 5s`, so you see exactly where to talk.
- **Recording against the picture:** open `ExamenPitchVideoV2-Guide` (teleprompter: current line, seconds left, next line), play it, and read.
- **Dropping in takes:** export each take as WAV and save it over the placeholder with the same name in `public/voiceover-v2/` (for example `vo_3_3.wav`). Trim leading silence so the file starts on the first word.
- **Live clip:** save it as `public/recordings-v2/live_reminder.mp4`, then in `src/Root.tsx` set `liveClipSrc: staticFile("recordings-v2/live_reminder.mp4")` in the `ExamenPitchVideoV2` default props (or in the Studio props panel). If the clip carries your real voice, keep `live_3_2.wav` silent so the line is not doubled.
- **Music:** `music_bed.wav` is a silent placeholder at volume 0.12. Use only licensed or royalty-free music (hackathon rule).
- **Changing the timing:** edit `src/v2/voiceover-v2.json` (`start`, `duration`, `text`). Keep each line inside its scene and at least 0.6 s from the scene edges (the crossfades). Subtitles and the teleprompter follow automatically. Run `npm run vo:placeholders -- --force` only before any take is recorded (it overwrites with silence).

```bash
npm run render:v2            # out/examen-pitch-v2.mp4        (final, with subtitles)
npm run render:v2-guide      # out/examen-pitch-v2-guide.mp4  (teleprompter version)
npm run render               # v1, unchanged: out/examen-pitch.mp4
```

### Files
| File | Role |
|---|---|
| `src/v2/voiceover-v2.json` | Scenes, line text, start and length (the timing source) |
| `src/v2/timeline.ts` | Turns the JSON into absolute frames |
| `src/v2/ExamenPitchVideoV2.tsx` | Master composition: scenes, crossfades, voiceover track, subtitles, guide |
| `src/v2/components/VoiceoverTrack.tsx` | One `<Audio>` per line + music bed |
| `src/v2/components/VoGuide.tsx` | Teleprompter overlay |
| `src/v2/scenes/V2Scene03_LiveReminder.tsx` | New live scene |
| `src/v2/scenes/V2Scene01/02/04–08_*.tsx` | v1 scene copies (re-timed; scene 07 updated for Danilo and real tool names) |
| `scripts/make-vo-placeholders.mjs` | Writes silent WAVs from the JSON |
| `public/voiceover-v2/` | Placeholder and recorded audio |

---

## 7. Accuracy notes (check before publishing)

- **Model names on screen** (Nova Micro gatekeeper, Claude 3.5 Sonnet) come from v1 and match `.env.example`, but the production deployment answers on **Nemotron Super 3 120B** in Bedrock us-east-1 ([17](17_aws_deployment_runbook.md)). The v2 voiceover avoids naming models; the visuals in scenes 02, 04, 05 and 08 still show them.
- **"Dario" (scene 05) and "Danilo" (scene 03)** are close names. Fine if intended; otherwise rename the scene 05 contact in `V2Scene05_Social.tsx`.
- **Numbers:** "over 580 automated tests" and "22 tools" match `AGENTS.MD` and `README.md`. The v2 voiceover says "just cents a day" because `README.md` estimates about $0.04/day for continuous listening; the v1 visuals and scene 08 tile still say "< $0.01 daily cost". Align the tile and the submission text with the figure you want to defend.

---

## 8. Real screen recording (Cap take 3, 2026-10-23)

Scenes 03–06 of `ExamenPitchVideoV2` now use a real recording of `https://examen.devgiov.com` instead of the mockups (prop `useRecordings`, default `true`; set it to `false` for the animated versions).

- **File:** `video-pitch/public/recordings-v2/cap_walkthrough_take3.mp4` (Cap Studio Mode, Window → *EXAMEN OS · Google Chrome*, 1920×1080, 3:36, with the presenter's microphone). `ScreenClip` crops the Chrome toolbar (top 229 px) so only the page shows.
- **The live line is real:** it was spoken to the Bee at 0:11.0–0:15.4 of the take. Bee delivered it and the pipeline created the task *"Contact Danilo and coordinate about the Hathathon"* (Bee misheard *hackathon*). Scene 03 plays the take's microphone audio for that line (prop `liveAudio`, default `true`), so it sits exactly on LIVE 3.2 (scene 5.0–9.4 s). Keep `live_3_2.wav` silent, or set `liveAudio: false` and record the line there.
- **The wait is cut, not faked:** speech ends at 0:15.4 and the task existed by about 0:48; the scene cuts with a "⏩ ~30 s later" chip.

| Scene | Scene time | Take time | Content |
|---|---|---|---|
| 03 Live | 0.0–10.2 s | 0:06.0–0:16.2 | Daily Routines, spoken line (audio on) |
| 03 Live | 10.2–16.5 s | 1:03.8–1:10.1 | Pending list; count turns 4/7 as the Bee task arrives |
| 03 Live | 16.5–26.0 s | 1:32.5–1:42.0 | The Danilo card with the heard quote |
| 04 Topics | 0–16 s | 1:58–2:14 | Dossier feed, Linear Regression dossier, citations |
| 04 Topics | 16–30 s | 2:15–2:29 | Echo Show view: folders, Tech Stack, Mesh Tastic dossier |
| 05 Social | 0–11 s | 3:05.5–3:16.5 | Danilo De Giovanni contact card |
| 05 Social | 11–24 s | — | Bilateral commitments mockup (VO 5.2 describes it) |
| 06 Peace | 0–7.5 s | 2:55.5–3:03 | Echo Show Peace of Mind |
| 06 Peace | 7.5–20 s | 3:19–3:31.5 | Dashboard ledger: Build Deployed, PR Merged |

Unused but available in the take: Echo Show Danilo (2:41–2:49), Echo Show Daily Routines (2:49–2:55).

### Found while recording
- **Dashboard did not refresh by itself** when the Bee task was created (the count stayed at 2 until the tab regained focus). The live SSE event for tasks created by the pipeline on AgentCore apparently does not reach the browser. Worth a look in `broadcast_event` for the AgentCore path.
- **"ASKED BY NONE · UNVERIFIED" badge** on the new card: the speaker attribution has `addressed_to_user` set with no name, and `SpeakerBadge` prints "None". Cosmetic.
- **Bee transcription:** "hackathon" became "Hathathon". You can fix the title with the edit (pencil) icon before a re-take, or leave it as evidence the capture is real.
- **Cap records the screen area of the window,** not its content: keep other windows (including the Claude app) off Chrome while recording.
- `cap_walkthrough.mp4` (take 2) in the same folder has the Claude app over the right third; it is not used.
