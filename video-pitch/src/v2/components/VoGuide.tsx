import React from "react";
import { useCurrentFrame } from "remotion";
import { THEME } from "../../constants";
import { PLACED_LINES, formatTime } from "../timeline";

// Teleprompter overlay for recording the voiceover against the picture.
// Only rendered by the ExamenPitchVideoV2-Guide composition.

export const VoGuide: React.FC = () => {
  const frame = useCurrentFrame();
  const current = PLACED_LINES.find(
    (l) => frame >= l.fromFrame && frame < l.fromFrame + l.plannedFrames,
  );
  const next = PLACED_LINES.find((l) => l.fromFrame > frame);
  const isLive = current?.kind === "live";

  return (
    <div
      style={{
        position: "absolute",
        left: 60,
        right: 60,
        bottom: 130,
        zIndex: 200,
        display: "flex",
        gap: 16,
        alignItems: "stretch",
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      }}
    >
      <div
        style={{
          width: 210,
          padding: "14px 18px",
          borderRadius: 14,
          backgroundColor: "rgba(0,0,0,0.82)",
          border: `2px solid ${current ? (isLive ? THEME.dangerRed : THEME.successGreen) : THEME.bgCardBorder}`,
          color: THEME.textPrimary,
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.08em", color: THEME.textSecondary }}>
          {formatTime(frame)}
        </div>
        <div
          style={{
            fontSize: 26,
            fontWeight: 800,
            color: current ? (isLive ? THEME.dangerRed : THEME.successGreen) : THEME.textMuted,
          }}
        >
          {current ? `${isLive ? "● LIVE" : "● VO"} ${current.id}` : "PAUSE"}
        </div>
        <div style={{ fontSize: 15, color: THEME.textSecondary }}>
          {current
            ? `${((current.fromFrame + current.plannedFrames - frame) / 30).toFixed(1)}s left of ${current.duration}s`
            : next
              ? `next in ${((next.fromFrame - frame) / 30).toFixed(1)}s`
              : "end"}
        </div>
      </div>
      <div
        style={{
          flex: 1,
          padding: "14px 22px",
          borderRadius: 14,
          backgroundColor: "rgba(0,0,0,0.82)",
          border: `1px solid ${THEME.bgCardBorder}`,
          color: THEME.textPrimary,
        }}
      >
        <div style={{ fontSize: 22, fontWeight: 700, lineHeight: 1.35 }}>
          {current ? current.text : <span style={{ color: THEME.textMuted }}>…</span>}
        </div>
        {next ? (
          <div style={{ fontSize: 15, color: THEME.textMuted, marginTop: 6 }}>
            NEXT {next.kind === "live" ? "LIVE" : "VO"} {next.id} @ {formatTime(next.fromFrame)}: {next.text}
          </div>
        ) : null}
      </div>
    </div>
  );
};
