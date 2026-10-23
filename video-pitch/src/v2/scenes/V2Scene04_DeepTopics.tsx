// v2 copy of src/scenes/Scene3_DeepTopics.tsx (v1 stays untouched).
// Subtitles come from the global voiceover track (src/v2/voiceover-v2.json).
import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { THEME } from "../../constants";
import { Background } from "../../components/Background";
import { HeaderBar } from "../../components/HeaderBar";

const SPEED = 1050 / 900;

export const V2Scene04_DeepTopics: React.FC = () => {
  // Same beats as v1, played faster to fit the shorter v2 slot (1050 -> 900 frames).
  const frame = Math.round(useCurrentFrame() * SPEED);
  const { fps } = useVideoConfig();

  const anim = spring({ frame, fps, config: { damping: 14 } });

  // Echo Show Modal slide-in (around frame 720)
  const echoModalProgress = spring({
    frame: frame - 720,
    fps,
    config: { damping: 13 },
  });

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Background />
      <HeaderBar currentSection="04 / Deep Topic Event Engine" />

      <div
        style={{
          position: "absolute",
          top: 110,
          left: 60,
          right: 60,
          bottom: 120,
          display: "flex",
          gap: 24,
          transform: `scale(${anim})`,
          opacity: anim,
        }}
      >
        {/* Left Side: Topic List */}
        <div
          style={{
            width: 380,
            borderRadius: 18,
            backgroundColor: "rgba(17, 24, 39, 0.9)",
            border: `1px solid ${THEME.bgCardBorder}`,
            padding: 24,
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
        >
          <div
            style={{
              fontSize: 14,
              fontWeight: 700,
              color: THEME.amazonOrange,
              textTransform: "uppercase",
              letterSpacing: "0.06em",
            }}
          >
            🧠 Topic Dossiers
          </div>

          {/* Active Item */}
          <div
            style={{
              padding: "16px 18px",
              borderRadius: 14,
              backgroundColor: "rgba(255, 153, 0, 0.1)",
              border: `1px solid ${THEME.amazonOrange}`,
            }}
          >
            <div style={{ fontSize: 16, fontWeight: 700, color: THEME.textPrimary, marginBottom: 6 }}>
              AWS Bedrock AgentCore & LangGraph
            </div>
            <div style={{ fontSize: 12, color: THEME.textSecondary, marginBottom: 10 }}>
              14 segments · 42m duration · 08:30 AM
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <span style={{ fontSize: 11, padding: "3px 8px", borderRadius: 6, backgroundColor: "rgba(16, 185, 129, 0.2)", color: "#6ee7b7" }}>
                SYNTHESIZED
              </span>
              <span style={{ fontSize: 11, padding: "3px 8px", borderRadius: 6, backgroundColor: "rgba(0, 164, 228, 0.2)", color: "#7dd3fc" }}>
                3 SOURCES
              </span>
            </div>
          </div>

          {/* Inactive Item 1 */}
          <div
            style={{
              padding: "16px 18px",
              borderRadius: 14,
              backgroundColor: "rgba(255, 255, 255, 0.03)",
              border: `1px solid ${THEME.bgCardBorder}`,
              opacity: 0.6,
            }}
          >
            <div style={{ fontSize: 15, fontWeight: 600, color: THEME.textPrimary, marginBottom: 4 }}>
              FastMCP Streamable HTTP 2025-11-25
            </div>
            <div style={{ fontSize: 12, color: THEME.textSecondary }}>
              6 segments · 18m duration
            </div>
          </div>

          {/* Inactive Item 2 */}
          <div
            style={{
              padding: "16px 18px",
              borderRadius: 14,
              backgroundColor: "rgba(255, 255, 255, 0.03)",
              border: `1px solid ${THEME.bgCardBorder}`,
              opacity: 0.6,
            }}
          >
            <div style={{ fontSize: 15, fontWeight: 600, color: THEME.textPrimary, marginBottom: 4 }}>
              Titan V2 Semantic Vector Search
            </div>
            <div style={{ fontSize: 12, color: THEME.textSecondary }}>
              4 segments · 12m duration
            </div>
          </div>
        </div>

        {/* Right Side: Dossier Detail Frame */}
        <div
          style={{
            flex: 1,
            borderRadius: 18,
            backgroundColor: "rgba(17, 24, 39, 0.95)",
            border: `1px solid ${THEME.bgCardBorder}`,
            padding: 36,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            position: "relative",
          }}
        >
          {/* Header */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
            <div>
              <div style={{ fontSize: 28, fontWeight: 800, color: THEME.textPrimary, marginBottom: 8 }}>
                AWS Bedrock AgentCore & LangGraph Architecture
              </div>
              <div style={{ fontSize: 14, color: THEME.textSecondary }}>
                Executive Technical Briefing · Extracted from ambient morning engineering sync
              </div>
            </div>
            <div
              style={{
                padding: "8px 16px",
                borderRadius: 20,
                backgroundColor: "rgba(0, 164, 228, 0.15)",
                border: `1px solid ${THEME.awsBlue}`,
                color: THEME.awsBlue,
                fontSize: 13,
                fontWeight: 600,
              }}
            >
              Claude 3.5 Sonnet Synthesis
            </div>
          </div>

          {/* Executive Summary Block */}
          <div
            style={{
              padding: 24,
              borderRadius: 14,
              backgroundColor: "rgba(0,0,0,0.3)",
              border: `1px solid rgba(255,255,255,0.06)`,
              marginBottom: 24,
            }}
          >
            <div style={{ fontSize: 14, fontWeight: 700, color: THEME.amazonOrange, marginBottom: 8, textTransform: "uppercase" }}>
              Key Takeaways
            </div>
            <ul style={{ margin: 0, paddingLeft: 20, fontSize: 15, color: THEME.textPrimary, lineHeight: 1.7 }}>
              <li>
                <strong>State-driven orchestration:</strong> LangGraph handles node transitions with fallback error recovery.
              </li>
              <li>
                <strong>Cloud runtime:</strong> AWS Bedrock AgentCore provides managed containerized execution for heavy agentic tasks.
              </li>
              <li>
                <strong>Cost optimization:</strong> Dual-tier model routing drops ambient idle cost to under $0.01 per day.
              </li>
            </ul>
          </div>

          {/* Web Sources Attached */}
          <div style={{ marginTop: "auto" }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: THEME.textSecondary, marginBottom: 12, textTransform: "uppercase" }}>
              🌐 Autonomous Web Research (DuckDuckGo Fallback Grounding)
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              <div style={{ padding: "8px 14px", borderRadius: 8, backgroundColor: "rgba(255,255,255,0.05)", border: `1px solid ${THEME.bgCardBorder}`, fontSize: 13, color: THEME.awsBlue }}>
                🔗 docs.aws.amazon.com/bedrock/agentcore
              </div>
              <div style={{ padding: "8px 14px", borderRadius: 8, backgroundColor: "rgba(255,255,255,0.05)", border: `1px solid ${THEME.bgCardBorder}`, fontSize: 13, color: THEME.awsBlue }}>
                🔗 langchain-ai.github.io/langgraph
              </div>
              <div style={{ padding: "8px 14px", borderRadius: 8, backgroundColor: "rgba(255,255,255,0.05)", border: `1px solid ${THEME.bgCardBorder}`, fontSize: 13, color: THEME.awsBlue }}>
                🔗 modelcontextprotocol.io/specification
              </div>
            </div>
          </div>

          {/* Echo Show Modal Overlay (appears at frame 720) */}
          {frame >= 720 && (
            <div
              style={{
                position: "absolute",
                top: 20,
                right: 20,
                width: 580,
                bottom: 20,
                borderRadius: 20,
                backgroundColor: "rgba(15, 23, 42, 0.98)",
                border: `2px solid ${THEME.amazonOrange}`,
                boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.7)",
                padding: 30,
                display: "flex",
                flexDirection: "column",
                transform: `translateX(${interpolate(echoModalProgress, [0, 1], [650, 0])}px)`,
                zIndex: 40,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <div style={{ fontSize: 14, fontWeight: 800, color: THEME.amazonOrange }}>
                  📺 ECHO SHOW 15 MULTI-MODAL PREVIEW
                </div>
                <div style={{ padding: "4px 10px", borderRadius: 12, backgroundColor: "rgba(255,153,0,0.2)", color: THEME.amazonOrange, fontSize: 11, fontWeight: 700 }}>
                  TOUCH UI
                </div>
              </div>

              <div style={{ fontSize: 20, fontWeight: 700, color: THEME.textPrimary, marginBottom: 12 }}>
                Meeting Briefing: AWS AgentCore
              </div>

              <div style={{ fontSize: 14, color: THEME.textSecondary, lineHeight: 1.6, flex: 1 }}>
                Voice prompt response from Alexa:
                <div style={{ padding: 14, borderRadius: 10, backgroundColor: "rgba(0,0,0,0.4)", color: "#e2e8f0", marginTop: 10, fontStyle: "italic" }}>
                  "I prepared an executive briefing on AWS AgentCore with official docs and 2 team action items."
                </div>
              </div>

              <div style={{ padding: "10px 14px", borderRadius: 8, backgroundColor: THEME.amazonOrange, color: "#000", fontWeight: 700, textAlign: "center", fontSize: 14 }}>
                Explore Full Dossier on Device
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
