// v2 copy of src/scenes/Scene7_Closing.tsx (v1 stays untouched).
// Subtitles come from the global voiceover track (src/v2/voiceover-v2.json).
import React from "react";
import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import { THEME } from "../../constants";
import { Background } from "../../components/Background";
import { HeaderBar } from "../../components/HeaderBar";

export const V2Scene08_Closing: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const anim = spring({ frame, fps, config: { damping: 12 } });

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Background />
      <HeaderBar currentSection="08 / Conclusion & Impact" />

      <div
        style={{
          position: "absolute",
          top: 110,
          left: 60,
          right: 60,
          bottom: 120,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          transform: `scale(${anim})`,
          opacity: anim,
        }}
      >
        <div
          style={{
            width: 80,
            height: 80,
            borderRadius: "50%",
            backgroundColor: THEME.amazonOrange,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 40,
            boxShadow: `0 0 50px ${THEME.amazonOrange}`,
            marginBottom: 16,
          }}
        >
          🐝
        </div>

        <div style={{ fontSize: 64, fontWeight: 900, color: THEME.textPrimary, letterSpacing: "-0.02em", marginBottom: 8 }}>
          EXAMEN
        </div>
        <div style={{ fontSize: 24, fontWeight: 600, color: THEME.amazonOrange, marginBottom: 36 }}>
          Ambient Executive Intelligence
        </div>

        {/* 4 Highlights Grid */}
        <div style={{ display: "flex", gap: 24, width: "100%", maxWidth: 1300, marginBottom: 40 }}>
          <div style={{ flex: 1, padding: 24, borderRadius: 16, backgroundColor: THEME.bgCard, border: `1px solid ${THEME.bgCardBorder}`, textAlign: "center" }}>
            <div style={{ fontSize: 36, fontWeight: 900, color: THEME.successGreen, marginBottom: 6 }}>
              588
            </div>
            <div style={{ fontSize: 14, color: THEME.textSecondary, fontWeight: 600 }}>
              Automated Tests (100% Green)
            </div>
          </div>

          <div style={{ flex: 1, padding: 24, borderRadius: 16, backgroundColor: THEME.bgCard, border: `1px solid ${THEME.bgCardBorder}`, textAlign: "center" }}>
            <div style={{ fontSize: 36, fontWeight: 900, color: THEME.amazonOrange, marginBottom: 6 }}>
              &lt; $0.01
            </div>
            <div style={{ fontSize: 14, color: THEME.textSecondary, fontWeight: 600 }}>
              Daily Cost (Nova Micro Gatekeeper)
            </div>
          </div>

          <div style={{ flex: 1, padding: 24, borderRadius: 16, backgroundColor: THEME.bgCard, border: `1px solid ${THEME.bgCardBorder}`, textAlign: "center" }}>
            <div style={{ fontSize: 36, fontWeight: 900, color: THEME.awsBlue, marginBottom: 6 }}>
              22
            </div>
            <div style={{ fontSize: 14, color: THEME.textSecondary, fontWeight: 600 }}>
              Live FastMCP Tools on AWS
            </div>
          </div>

          <div style={{ flex: 1, padding: 24, borderRadius: 16, backgroundColor: THEME.bgCard, border: `1px solid ${THEME.bgCardBorder}`, textAlign: "center" }}>
            <div style={{ fontSize: 36, fontWeight: 900, color: THEME.purpleAccent, marginBottom: 6 }}>
              Multi-Tenant
            </div>
            <div style={{ fontSize: 14, color: THEME.textSecondary, fontWeight: 600 }}>
              Amazon DynamoDB & Session Auth
            </div>
          </div>
        </div>

        {/* Technology Stack Footer */}
        <div style={{ display: "flex", gap: 20, alignItems: "center" }}>
          <span style={{ fontSize: 15, color: THEME.textMuted }}>Powered by:</span>
          <span style={{ fontSize: 16, fontWeight: 700, color: THEME.textPrimary }}>Bee Wearable AI</span>
          <span style={{ color: THEME.textMuted }}>•</span>
          <span style={{ fontSize: 16, fontWeight: 700, color: THEME.awsBlue }}>AWS Bedrock & AgentCore</span>
          <span style={{ color: THEME.textMuted }}>•</span>
          <span style={{ fontSize: 16, fontWeight: 700, color: THEME.amazonOrange }}>Amazon DynamoDB</span>
          <span style={{ color: THEME.textMuted }}>•</span>
          <span style={{ fontSize: 16, fontWeight: 700, color: THEME.successGreen }}>Next.js 14 & FastMCP</span>
        </div>
      </div>
    </div>
  );
};
