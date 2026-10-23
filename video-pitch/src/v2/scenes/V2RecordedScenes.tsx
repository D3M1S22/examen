import React from "react";
import { Video } from "@remotion/media";
import { Easing, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { THEME } from "../../constants";
import { Background } from "../../components/Background";
import { HeaderBar } from "../../components/HeaderBar";
import { Chip, ClipHeight, ScreenClip, TAKE3 } from "../components/ScreenClip";
import { V2Scene05_Social } from "./V2Scene05_Social";

// Scenes 03–06 built from the real Cap recording of examen.devgiov.com
// (public/recordings-v2/cap_walkthrough_take3.mp4, 3:36, Chrome only).
// Clip times below are seconds into that recording. Map: docs/19 §8.

const CLIP_TOP = 112;
const CLIP_H = ClipHeight(1800);
const CLIP_BOTTOM = CLIP_TOP + CLIP_H;

/** Fades a chip in at `from` and out at `to` (scene seconds). */
const Timed: React.FC<{ from: number; to: number; children: React.ReactNode; style?: React.CSSProperties }> = ({
  from,
  to,
  children,
  style,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = interpolate(frame, [from * fps, from * fps + 8, to * fps - 8, to * fps], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const lift = interpolate(frame, [from * fps, from * fps + 12], [12, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  return <div style={{ position: "absolute", opacity, translate: `0px ${lift}px`, zIndex: 20, ...style }}>{children}</div>;
};

// ---------------------------------------------------------------------------
// 03 · LIVE: the presenter says the reminder to the Bee; the task lands in Daily Routines.
// Segment A keeps the take's microphone audio: the real spoken line is at 11.0–15.4 s of the
// recording, i.e. scene 5.0–9.4 s, where LIVE 3.2 sits in voiceover-v2.json.
// ---------------------------------------------------------------------------
const PIPELINE = [
  { at: 10.8, label: "Bee new-utterance", color: THEME.amazonOrange },
  { at: 11.8, label: "Gatekeeper · scheduled_task", color: THEME.awsBlue },
  { at: 12.8, label: "Scheduler · PlannedTask", color: THEME.purpleAccent },
  { at: 13.8, label: "AgentCore → DynamoDB", color: THEME.successGreen },
];

export const V2Scene03_LiveRecorded: React.FC<{ liveAudio?: boolean }> = ({ liveAudio = true }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const banner = spring({ frame: frame - 19.8 * fps, fps, config: { damping: 200 } });

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Background />
      <HeaderBar currentSection="03 / Live Demo · Bee → Daily Routines" />
      <ScreenClip
        top={CLIP_TOP}
        segments={[
          { at: 0, clipStart: 6.0, duration: 10.2, volume: liveAudio ? 1 : 0, name: "Live: speaking to Bee" },
          { at: 10.2, clipStart: 63.8, duration: 6.3, name: "Live: task arrives (4/7)" },
          { at: 16.5, clipStart: 92.5, duration: 9.5, name: "Live: Danilo card" },
        ]}
      />

      {/* Always-on badge */}
      <Timed from={0} to={26} style={{ top: CLIP_TOP + 86, left: 80 }}>
        <Chip color={THEME.dangerRed}>● LIVE · real Bee capture · no wake word</Chip>
      </Timed>

      <Timed from={4.6} to={10.2} style={{ top: CLIP_BOTTOM - 80, left: 80 }}>
        <Chip>🎙 Spoken to the Bee: “Remind me to contact Danilo…”</Chip>
      </Timed>

      <Timed from={10.2} to={16.4} style={{ top: CLIP_TOP + 86, right: 80 }}>
        <Chip color={THEME.textSecondary}>⏩ ~30 s later · Bee delivery + pipeline</Chip>
      </Timed>

      {/* Pipeline steps */}
      <div style={{ position: "absolute", left: 80, top: CLIP_BOTTOM - 80, display: "flex", gap: 12, zIndex: 20 }}>
        {PIPELINE.map((p) => {
          const on = spring({ frame: frame - p.at * fps, fps, config: { damping: 200 } });
          const out = interpolate(frame, [17.5 * fps, 18 * fps], [1, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          return (
            <div key={p.label} style={{ opacity: on * out, scale: interpolate(on, [0, 1], [0.9, 1]) }}>
              <Chip color={p.color}>✓ {p.label}</Chip>
            </div>
          );
        })}
      </div>

      <Timed from={17.6} to={26} style={{ top: CLIP_TOP + 86, right: 80 }}>
        <Chip color={THEME.successGreen}>✓ New task in Daily Routines · from your voice</Chip>
      </Timed>

      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: CLIP_BOTTOM - 84,
          display: "flex",
          justifyContent: "flex-end",
          paddingRight: 80,
          opacity: banner,
          zIndex: 21,
        }}
      >
        <Chip style={{ fontSize: 22 }}>Said once. Captured, tracked, linked to Danilo. Zero taps.</Chip>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 04 · Topic Dossiers (dashboard) then the Echo Show view.
// ---------------------------------------------------------------------------
export const V2Scene04_TopicsRecorded: React.FC = () => (
  <div style={{ position: "relative", width: "100%", height: "100%" }}>
    <Background />
    <HeaderBar currentSection="04 / Deep Topic Event Engine" />
    <ScreenClip
      top={CLIP_TOP}
      segments={[
        { at: 0, clipStart: 118.0, duration: 16.0, name: "Topics: dossier feed + citations" },
        { at: 16.0, clipStart: 135.0, duration: 14.0, name: "Topics: Echo Show view" },
      ]}
    />
    <Timed from={0.4} to={9.8} style={{ top: CLIP_TOP + 86, right: 80 }}>
      <Chip color={THEME.awsBlue}>Executive dossiers · built from meetings</Chip>
    </Timed>
    <Timed from={10} to={15.8} style={{ top: CLIP_TOP + 86, right: 80 }}>
      <Chip color={THEME.successGreen}>Autonomous web research · cited sources</Chip>
    </Timed>
    <Timed from={16.2} to={30} style={{ top: CLIP_TOP + 86, right: 80 }}>
      <Chip>Echo Show 15 touch view</Chip>
    </Timed>
  </div>
);

// ---------------------------------------------------------------------------
// 05 · Social Rolodex: the real Danilo card, then the bilateral-commitments mockup (VO 5.2).
// ---------------------------------------------------------------------------
export const V2Scene05_SocialRecorded: React.FC = () => {
  const { fps } = useVideoConfig();
  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Background />
      <HeaderBar currentSection="05 / Social Rolodex & Bilateral Promises" />
      <ScreenClip
        top={CLIP_TOP}
        segments={[{ at: 0, clipStart: 185.5, duration: 11.0, name: "Social: Danilo card (dashboard)" }]}
      />
      <Timed from={0.4} to={10.8} style={{ top: CLIP_TOP + 86, right: 80 }}>
        <Chip color={THEME.awsBlue}>Contacts enriched from conversations</Chip>
      </Timed>
      <Sequence from={Math.round(11 * fps)} name="Social: commitments (animated)">
        <V2Scene05_Social />
      </Sequence>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 06 · Peace of Mind: Echo Show card, then the dashboard ledger.
// ---------------------------------------------------------------------------
export const V2Scene06_PeaceRecorded: React.FC = () => (
  <div style={{ position: "relative", width: "100%", height: "100%" }}>
    <Background />
    <HeaderBar currentSection="06 / Peace of Mind & Speaker Verification" />
    <ScreenClip
      top={CLIP_TOP}
      segments={[
        { at: 0, clipStart: 175.5, duration: 7.5, name: "Peace: Echo Show" },
        { at: 7.5, clipStart: 199.0, duration: 12.5, name: "Peace: dashboard ledger" },
      ]}
    />
    <Timed from={0.4} to={7.4} style={{ top: CLIP_TOP + 86, right: 80 }}>
      <Chip color={THEME.successGreen}>Verified from your own words</Chip>
    </Timed>
    <Timed from={7.6} to={20} style={{ top: CLIP_TOP + 86, right: 80 }}>
      <Chip color={THEME.successGreen}>Timestamp · transcript · confidence</Chip>
    </Timed>
  </div>
);

// ---------------------------------------------------------------------------
// The whole uncut take with a timecode, for browsing it in Studio.
// ---------------------------------------------------------------------------
const Timecode: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const m = Math.floor(t / 60);
  const s = (t - m * 60).toFixed(1).padStart(4, "0");
  return (
    <div style={{ position: "absolute", left: 24, bottom: 24, zIndex: 10 }}>
      <Chip color={THEME.textPrimary} style={{ fontFamily: "monospace", fontSize: 28 }}>
        take 3 · {m}:{s}
      </Chip>
    </div>
  );
};

export const RawTake: React.FC = () => (
  <div style={{ position: "relative", width: "100%", height: "100%", backgroundColor: "#000" }}>
    <Video src={staticFile(TAKE3)} style={{ width: "100%", height: "100%" }} />
    <Timecode />
  </div>
);
