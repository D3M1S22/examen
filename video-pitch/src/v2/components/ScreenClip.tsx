import React from "react";
import { Video } from "@remotion/media";
import { Sequence, staticFile, useVideoConfig } from "remotion";
import { THEME } from "../../constants";

// Real screen recording of the EXAMEN dashboard (Cap, Chrome window, 1920×1080 export).
// The export shows the whole Chrome window; CHROME_UI_PX crops away the tab strip,
// toolbar, bookmarks bar and banner so only the web page is visible.

export const TAKE3 = "recordings-v2/cap_walkthrough_take3.mp4";
const SRC_W = 1920;
const SRC_H = 1080;
const CHROME_UI_PX = 229;
const PAGE_ASPECT = SRC_W / (SRC_H - CHROME_UI_PX);

export interface ClipSegment {
  /** Seconds from the start of the scene. */
  at: number;
  /** Seconds into the recording. */
  clipStart: number;
  duration: number;
  /** 0 = muted (default). The take has the presenter's microphone. */
  volume?: number;
  name?: string;
}

export const ScreenClip: React.FC<{
  segments: ClipSegment[];
  width?: number;
  top?: number;
  src?: string;
}> = ({ segments, width = 1800, top = 112, src = TAKE3 }) => {
  const { fps } = useVideoConfig();
  const height = Math.round(width / PAGE_ASPECT);
  const scale = width / SRC_W;

  return (
    <div
      style={{
        position: "absolute",
        top,
        left: (1920 - width) / 2,
        width,
        height,
        borderRadius: 18,
        overflow: "hidden",
        border: `1px solid ${THEME.bgCardBorder}`,
        boxShadow: "0 30px 80px rgba(0,0,0,0.55)",
        backgroundColor: "#0b0f17",
      }}
    >
      {segments.map((seg) => (
        <Sequence
          key={`${seg.at}-${seg.clipStart}`}
          name={seg.name ?? `Recording ${seg.clipStart}s`}
          from={Math.round(seg.at * fps)}
          durationInFrames={Math.round(seg.duration * fps)}
          layout="none"
        >
          <div
            style={{
              position: "absolute",
              left: 0,
              top: -CHROME_UI_PX * scale,
              width,
              height: SRC_H * scale,
            }}
          >
            <Video
              src={staticFile(src)}
              trimBefore={Math.round(seg.clipStart * fps)}
              volume={seg.volume ?? 0}
              objectFit="cover"
              style={{ width: "100%", height: "100%" }}
            />
          </div>
        </Sequence>
      ))}
    </div>
  );
};

export const ClipHeight = (width = 1800) => Math.round(width / PAGE_ASPECT);

/** Small label chip drawn over the recording. */
export const Chip: React.FC<{
  children: React.ReactNode;
  color?: string;
  style?: React.CSSProperties;
}> = ({ children, color = THEME.amazonOrange, style }) => (
  <div
    style={{
      padding: "8px 16px",
      borderRadius: 22,
      backgroundColor: "rgba(8, 12, 20, 0.88)",
      border: `1px solid ${color}`,
      color,
      fontSize: 18,
      fontWeight: 800,
      letterSpacing: "0.04em",
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      boxShadow: "0 8px 24px rgba(0,0,0,0.45)",
      ...style,
    }}
  >
    {children}
  </div>
);
