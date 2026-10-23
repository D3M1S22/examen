import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { THEME } from "../constants";
import { SubtitleCue } from "../types";

interface SubtitlesProps {
  cues: SubtitleCue[];
}

export const Subtitles: React.FC<SubtitlesProps> = ({ cues }) => {
  const frame = useCurrentFrame();

  const currentCue = cues.find(
    (cue) => frame >= cue.fromFrame && frame < cue.toFrame
  );

  if (!currentCue) {
    return null;
  }

  // Fade-in during first 10 frames of cue, fade-out during last 8 frames
  const cueProgress = frame - currentCue.fromFrame;
  const cueDuration = currentCue.toFrame - currentCue.fromFrame;
  const opacity = interpolate(
    cueProgress,
    [0, 10, cueDuration - 8, cueDuration],
    [0, 1, 1, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  return (
    <div
      style={{
        position: "absolute",
        bottom: 40,
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        zIndex: 100,
        pointerEvents: "none",
        opacity,
      }}
    >
      <div
        style={{
          maxWidth: 1200,
          padding: "14px 28px",
          borderRadius: 16,
          backgroundColor: "rgba(10, 15, 25, 0.88)",
          backdropFilter: "blur(12px)",
          border: `1px solid rgba(255, 255, 255, 0.12)`,
          boxShadow: "0 10px 30px rgba(0, 0, 0, 0.5)",
          textAlign: "center",
        }}
      >
        <span
          style={{
            fontSize: 22,
            fontWeight: 600,
            lineHeight: 1.4,
            color: THEME.textPrimary,
            letterSpacing: "0.01em",
          }}
        >
          {currentCue.text}
        </span>
      </div>
    </div>
  );
};

