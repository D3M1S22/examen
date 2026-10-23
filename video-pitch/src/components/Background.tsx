import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { THEME } from "../constants";

export const Background: React.FC = () => {
  const frame = useCurrentFrame();

  // Gentle ambient pulsing glow
  const glowOpacity1 = interpolate(
    Math.sin(frame / 45),
    [-1, 1],
    [0.15, 0.28],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const glowOpacity2 = interpolate(
    Math.cos(frame / 60),
    [-1, 1],
    [0.1, 0.22],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        backgroundColor: THEME.bg,
        overflow: "hidden",
        fontFamily:
          '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      }}
    >
      {/* Background Radial Glow 1 (AWS Blue) */}
      <div
        style={{
          position: "absolute",
          top: "-15%",
          left: "20%",
          width: 900,
          height: 900,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${THEME.awsBlue} 0%, rgba(0,0,0,0) 70%)`,
          opacity: glowOpacity1,
          filter: "blur(90px)",
          pointerEvents: "none",
        }}
      />

      {/* Background Radial Glow 2 (Amazon Orange) */}
      <div
        style={{
          position: "absolute",
          bottom: "-20%",
          right: "15%",
          width: 850,
          height: 850,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${THEME.amazonOrange} 0%, rgba(0,0,0,0) 70%)`,
          opacity: glowOpacity2,
          filter: "blur(100px)",
          pointerEvents: "none",
        }}
      />

      {/* Subtle Grid Pattern Overlay */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
          backgroundImage:
            "linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
          pointerEvents: "none",
        }}
      />
    </div>
  );
};

