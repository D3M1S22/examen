// v2 copy of src/scenes/Scene5_PeaceOfMind.tsx (v1 stays untouched).
// Subtitles come from the global voiceover track (src/v2/voiceover-v2.json).
import React from "react";
import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import { THEME } from "../../constants";
import { Background } from "../../components/Background";
import { HeaderBar } from "../../components/HeaderBar";

const SPEED = 750 / 600;

export const V2Scene06_PeaceOfMind: React.FC = () => {
  // Same beats as v1, played faster to fit the shorter v2 slot (750 -> 600 frames).
  const frame = Math.round(useCurrentFrame() * SPEED);
  const { fps } = useVideoConfig();

  const p1 = spring({ frame: frame - 10, fps, config: { damping: 14 } });
  const p2 = spring({ frame: frame - 380, fps, config: { damping: 14 } });

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Background />
      <HeaderBar currentSection="06 / Peace of Mind & Speaker Verification" />

      <div
        style={{
          position: "absolute",
          top: 120,
          left: 60,
          right: 60,
          bottom: 120,
          display: "flex",
          gap: 30,
        }}
      >
        {/* Left Side: Certified Action-State Events */}
        <div
          style={{
            flex: 1.1,
            borderRadius: 20,
            backgroundColor: "rgba(17, 24, 39, 0.95)",
            border: `1px solid ${THEME.bgCardBorder}`,
            padding: 36,
            display: "flex",
            flexDirection: "column",
            transform: `scale(${p1})`,
            opacity: p1,
          }}
        >
          <div
            style={{
              fontSize: 13,
              fontWeight: 700,
              color: THEME.successGreen,
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              marginBottom: 10,
            }}
          >
            🛡️ Certified Action-State Verification
          </div>
          <div style={{ fontSize: 26, fontWeight: 800, color: THEME.textPrimary, marginBottom: 8 }}>
            Zero Anxiety, Zero Lost Time
          </div>
          <div style={{ fontSize: 14, color: THEME.textSecondary, marginBottom: 26 }}>
            Auditable physical action states certified from ambient speech with exact timestamps
          </div>

          {/* Action Card 1: Iron */}
          <div
            style={{
              padding: "18px 20px",
              borderRadius: 14,
              backgroundColor: "rgba(16, 185, 129, 0.08)",
              border: `1px solid rgba(16, 185, 129, 0.3)`,
              marginBottom: 16,
              display: "flex",
              alignItems: "center",
              gap: 16,
            }}
          >
            <div style={{ fontSize: 32 }}>🔌</div>
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 17, fontWeight: 700, color: THEME.textPrimary }}>
                  Clothes Iron Unplugged
                </span>
                <span style={{ padding: "3px 8px", borderRadius: 6, backgroundColor: THEME.successGreen, color: "#000", fontSize: 11, fontWeight: 800 }}>
                  CONFIRMED
                </span>
              </div>
              <div style={{ fontSize: 13, color: "#6ee7b7", marginTop: 4 }}>
                Today at 08:14:22 · Verbatim: "Iron unplugged, heading out"
              </div>
            </div>
          </div>

          {/* Action Card 2: Door */}
          <div
            style={{
              padding: "18px 20px",
              borderRadius: 14,
              backgroundColor: "rgba(16, 185, 129, 0.08)",
              border: `1px solid rgba(16, 185, 129, 0.3)`,
              marginBottom: 16,
              display: "flex",
              alignItems: "center",
              gap: 16,
            }}
          >
            <div style={{ fontSize: 32 }}>🔐</div>
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 17, fontWeight: 700, color: THEME.textPrimary }}>
                  Front Door Locked
                </span>
                <span style={{ padding: "3px 8px", borderRadius: 6, backgroundColor: THEME.successGreen, color: "#000", fontSize: 11, fontWeight: 800 }}>
                  CONFIRMED
                </span>
              </div>
              <div style={{ fontSize: 13, color: "#6ee7b7", marginTop: 4 }}>
                Today at 08:16:05 · Verbatim: "Double-locked the front door"
              </div>
            </div>
          </div>

          {/* Action Card 3: Keys */}
          <div
            style={{
              padding: "18px 20px",
              borderRadius: 14,
              backgroundColor: "rgba(16, 185, 129, 0.08)",
              border: `1px solid rgba(16, 185, 129, 0.3)`,
              display: "flex",
              alignItems: "center",
              gap: 16,
            }}
          >
            <div style={{ fontSize: 32 }}>🔑</div>
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 17, fontWeight: 700, color: THEME.textPrimary }}>
                  Car & Office Keys Taken
                </span>
                <span style={{ padding: "3px 8px", borderRadius: 6, backgroundColor: THEME.successGreen, color: "#000", fontSize: 11, fontWeight: 800 }}>
                  CONFIRMED
                </span>
              </div>
              <div style={{ fontSize: 13, color: "#6ee7b7", marginTop: 4 }}>
                Today at 08:15:30
              </div>
            </div>
          </div>
        </div>

        {/* Right Side: Speaker Review & Privacy Drawer (appears at frame 380) */}
        <div
          style={{
            flex: 0.9,
            borderRadius: 20,
            backgroundColor: "rgba(17, 24, 39, 0.95)",
            border: `1px solid ${frame >= 380 ? THEME.amazonOrange : THEME.bgCardBorder}`,
            boxShadow: frame >= 380 ? "0 0 35px rgba(255, 153, 0, 0.15)" : "none",
            padding: 36,
            display: "flex",
            flexDirection: "column",
            transform: `scale(${frame >= 380 ? p2 : 0.95})`,
            opacity: frame >= 380 ? p2 : 0.3,
          }}
        >
          <div
            style={{
              fontSize: 13,
              fontWeight: 700,
              color: THEME.amazonOrange,
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              marginBottom: 10,
            }}
          >
            🎙️ Speaker Review & Privacy
          </div>
          <div style={{ fontSize: 24, fontWeight: 800, color: THEME.textPrimary, marginBottom: 8 }}>
            Untagged Speech Curation
          </div>
          <div style={{ fontSize: 14, color: THEME.textSecondary, marginBottom: 24 }}>
            Guarantees privacy & data integrity: unverified speech requires explicit user confirmation
          </div>

          {/* Pending Review Item */}
          <div
            style={{
              padding: 22,
              borderRadius: 14,
              backgroundColor: "rgba(255, 255, 255, 0.04)",
              border: "1px dashed rgba(255, 153, 0, 0.4)",
              marginBottom: 20,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
              <span style={{ fontSize: 12, fontWeight: 700, color: THEME.amazonOrange, textTransform: "uppercase" }}>
                Pending Review #482
              </span>
              <span style={{ fontSize: 12, color: THEME.textMuted }}>11:42 AM</span>
            </div>
            <div style={{ fontSize: 15, fontStyle: "italic", color: THEME.textPrimary, marginBottom: 16 }}>
              "We need to verify the DynamoDB configuration before the final demo."
            </div>

            <div style={{ display: "flex", gap: 12 }}>
              <div
                style={{
                  flex: 1,
                  padding: "10px 0",
                  borderRadius: 8,
                  backgroundColor: THEME.amazonOrange,
                  color: "#000",
                  fontWeight: 700,
                  fontSize: 13,
                  textAlign: "center",
                }}
              >
                ✓ Accept (Assign to Me)
              </div>
              <div
                style={{
                  flex: 0.8,
                  padding: "10px 0",
                  borderRadius: 8,
                  backgroundColor: "rgba(255,255,255,0.08)",
                  color: THEME.textSecondary,
                  fontWeight: 600,
                  fontSize: 13,
                  textAlign: "center",
                }}
              >
                ✕ Dismiss
              </div>
            </div>
          </div>

          <div
            style={{
              marginTop: "auto",
              padding: "14px 16px",
              borderRadius: 12,
              backgroundColor: "rgba(0, 164, 228, 0.1)",
              border: `1px solid rgba(0, 164, 228, 0.25)`,
              color: THEME.awsBlue,
              fontSize: 13,
            }}
          >
            🔒 Multi-user tenant isolation: each user's speech and review queue is isolated in Amazon DynamoDB.
          </div>
        </div>
      </div>
    </div>
  );
};
