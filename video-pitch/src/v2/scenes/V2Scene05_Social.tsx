// v2 copy of src/scenes/Scene4_SocialCommitments.tsx (v1 stays untouched).
// Subtitles come from the global voiceover track (src/v2/voiceover-v2.json).
import React from "react";
import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import { THEME } from "../../constants";
import { Background } from "../../components/Background";
import { HeaderBar } from "../../components/HeaderBar";

const SPEED = 900 / 720;

export const V2Scene05_Social: React.FC = () => {
  // Same beats as v1, played faster to fit the shorter v2 slot (900 -> 720 frames).
  const frame = Math.round(useCurrentFrame() * SPEED);
  const { fps } = useVideoConfig();

  const c1 = spring({ frame: frame - 10, fps, config: { damping: 14 } });
  const c2 = spring({ frame: frame - 400, fps, config: { damping: 14 } });

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Background />
      <HeaderBar currentSection="05 / Social Rolodex & Bilateral Promises" />

      <div
        style={{
          position: "absolute",
          top: 120,
          left: 60,
          right: 60,
          bottom: 120,
          display: "flex",
          gap: 30,
          alignItems: "stretch",
        }}
      >
        {/* Left Side: Contact Card & Commitments */}
        <div
          style={{
            flex: 1,
            borderRadius: 20,
            backgroundColor: "rgba(17, 24, 39, 0.95)",
            border: `1px solid ${THEME.bgCardBorder}`,
            padding: 36,
            display: "flex",
            flexDirection: "column",
            transform: `scale(${c1})`,
            opacity: c1,
          }}
        >
          {/* Contact Header */}
          <div style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 24 }}>
            <div
              style={{
                width: 64,
                height: 64,
                borderRadius: "50%",
                backgroundColor: "rgba(255, 153, 0, 0.2)",
                border: `2px solid ${THEME.amazonOrange}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 28,
              }}
            >
              👨‍💻
            </div>
            <div>
              <div style={{ fontSize: 26, fontWeight: 800, color: THEME.textPrimary }}>
                Dario
              </div>
              <div style={{ fontSize: 15, color: THEME.textSecondary }}>
                Tech Lead @ CloudScale · Met at Tech Coworking
              </div>
            </div>
          </div>

          <div
            style={{
              fontSize: 13,
              fontWeight: 700,
              color: THEME.amazonOrange,
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              marginBottom: 12,
            }}
          >
            🤝 Bilateral Commitments Engine
          </div>

          {/* I Owe Dario */}
          <div
            style={{
              padding: "20px 22px",
              borderRadius: 14,
              backgroundColor: "rgba(239, 68, 68, 0.1)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              marginBottom: 16,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: THEME.dangerRed, textTransform: "uppercase" }}>
                I Owe Dario (Debtor: User)
              </span>
              <span style={{ fontSize: 12, color: "#fca5a5", fontWeight: 600 }}>DUE TODAY 17:00</span>
            </div>
            <div style={{ fontSize: 16, fontWeight: 700, color: THEME.textPrimary }}>
              "Send repository documentation and migration schema"
            </div>
          </div>

          {/* Dario Owes Me */}
          <div
            style={{
              padding: "20px 22px",
              borderRadius: 14,
              backgroundColor: "rgba(16, 185, 129, 0.1)",
              border: "1px solid rgba(16, 185, 129, 0.3)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: THEME.successGreen, textTransform: "uppercase" }}>
                Dario Owes Me (Creditor: User)
              </span>
              <span style={{ fontSize: 12, color: "#6ee7b7", fontWeight: 600 }}>DUE FRIDAY</span>
            </div>
            <div style={{ fontSize: 16, fontWeight: 700, color: THEME.textPrimary }}>
              "Review architecture on AWS Bedrock"
            </div>
          </div>
        </div>

        {/* Right Side: Auto-Scheduled Daily Routine / Task (appears at frame 400) */}
        <div
          style={{
            flex: 1,
            borderRadius: 20,
            backgroundColor: "rgba(17, 24, 39, 0.95)",
            border: `1px solid ${frame >= 400 ? THEME.amazonOrange : THEME.bgCardBorder}`,
            boxShadow: frame >= 400 ? "0 0 35px rgba(255, 153, 0, 0.15)" : "none",
            padding: 36,
            display: "flex",
            flexDirection: "column",
            transform: `scale(${frame >= 400 ? c2 : 0.95})`,
            opacity: frame >= 400 ? c2 : 0.3,
          }}
        >
          <div
            style={{
              fontSize: 13,
              fontWeight: 700,
              color: THEME.awsBlue,
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              marginBottom: 12,
            }}
          >
            ⏰ Ambient Scheduled Tasks
          </div>
          <div style={{ fontSize: 24, fontWeight: 800, color: THEME.textPrimary, marginBottom: 8 }}>
            Daily Routines & Follow-ups
          </div>
          <div style={{ fontSize: 14, color: THEME.textSecondary, marginBottom: 24 }}>
            Voice promises automatically transformed into tracked, actionable tasks
          </div>

          {/* Extracted Task Item */}
          <div
            style={{
              padding: 22,
              borderRadius: 14,
              backgroundColor: "rgba(0,0,0,0.3)",
              border: `1px solid rgba(255, 255, 255, 0.08)`,
              display: "flex",
              alignItems: "center",
              gap: 16,
              marginBottom: 16,
            }}
          >
            <div
              style={{
                width: 24,
                height: 24,
                borderRadius: 6,
                border: `2px solid ${THEME.amazonOrange}`,
              }}
            />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 16, fontWeight: 700, color: THEME.textPrimary }}>
                Send repo docs to Dario (CloudScale)
              </div>
              <div style={{ fontSize: 13, color: THEME.textSecondary, marginTop: 4 }}>
                Source: Ambient dialogue · Auto-scheduled for 17:00
              </div>
            </div>
            <div
              style={{
                padding: "6px 12px",
                borderRadius: 12,
                backgroundColor: "rgba(16, 185, 129, 0.15)",
                color: "#6ee7b7",
                fontSize: 12,
                fontWeight: 700,
              }}
            >
              98% CONFIDENCE
            </div>
          </div>

          <div
            style={{
              marginTop: "auto",
              padding: 16,
              borderRadius: 12,
              backgroundColor: "rgba(255, 153, 0, 0.08)",
              border: "1px dashed rgba(255, 153, 0, 0.4)",
              color: THEME.textPrimary,
              fontSize: 14,
              display: "flex",
              alignItems: "center",
              gap: 12,
            }}
          >
            <span>💡</span>
            <span>
              Zero manual typing required. Bilateral roles, deadlines, and context resolved by Claude 3.5 Sonnet.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
