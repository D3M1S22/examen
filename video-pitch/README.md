# 🎬 EXAMEN — Remotion Video Pitch (3 Minutes)

This project contains the complete programmatic **Remotion video pitch** for EXAMEN, structured according to [docs/18_video_pitch_script_and_production_guide.md](../docs/18_video_pitch_script_and_production_guide.md).

## 🚀 Quick Start

### 1. Launch Remotion Studio (Interactive Preview)

```bash
cd video-pitch
npm run dev
```

This launches Remotion Studio in your browser (default: `http://localhost:3000`).  
You can scrub through the timeline, inspect individual frames, preview transitions, and toggle subtitles.

### 2. Composition Layout

- **`ExamenPitchVideo`**: The full master 3-minute video (5310 frames @ 30 fps = 2m 57s, with smooth 0.5s crossfades).
- **`Scene1-Problem`**: Vision & Cognitive Overload (30s).
- **`Scene2-Architecture`**: Bee Wearable & AWS Bedrock Gatekeeper (30s).
- **`Scene3-DeepTopics`**: Live Demo: Deep Topic Event Engine & Echo Show View (35s).
- **`Scene4-SocialCommitments`**: Live Demo: Social Rolodex & Bilateral Promises (30s).
- **`Scene5-PeaceOfMind`**: Live Demo: Peace of Mind & Speaker Verification (25s).
- **`Scene6-AlexaMCP`**: Alexa+ FastMCP 22 Tools on AWS (15s).
- **`Scene7-Closing`**: Hackathon Metrics & Stack Recap (15s).

### 3. Adding Live Screen Recordings

If you record video clips of `https://examen.devgiov.com`, you can drop them into `public/recordings/` and import them via `<Video src={staticFile("recordings/your_clip.mp4")} />`. By default, high-fidelity animated UI mockups are rendered automatically.

### 4. Render to Final MP4

When you are ready to export the final high-definition MP4:

```bash
cd video-pitch
npm run render
```

The output file will be generated at `out/examen-pitch.mp4` (1080p, 30 fps, H.264).

---

## 🆕 v2 — Live Demo Edition (2:54.5)

v1 above is unchanged. v2 lives in `src/v2/` (Studio folder **v2**) and adds a live example: you say *"Remind me to contact Danilo and coordinate about the hackathon submission"* and it lands in Daily Routines.

- **`ExamenPitchVideoV2`**: final v2 video with subtitles and a voiceover track (one audio clip per line).
- **`ExamenPitchVideoV2-Guide`**: same video with a teleprompter overlay, for recording the voiceover.
- **`V2Scene03-LiveReminder`**: the new live scene alone.

```bash
npm run vo:placeholders   # silent WAVs in public/voiceover-v2/ (creates missing files only)
npm run dev               # preview
npm run render:v2         # out/examen-pitch-v2.mp4
```

Script, line-by-line timing and the recording checklist: [docs/19_video_pitch_v2_script_live_demo.md](../docs/19_video_pitch_v2_script_live_demo.md). Timing source: `src/v2/voiceover-v2.json`.
