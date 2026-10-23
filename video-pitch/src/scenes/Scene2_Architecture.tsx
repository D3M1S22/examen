import React from "react";
import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import { THEME } from "../constants";
import { SubtitleCue } from "../types";
import { Background } from "../components/Background";
import { HeaderBar } from "../components/HeaderBar";
import { Subtitles } from "../components/Subtitles";

export const SCENE_2_CUES: SubtitleCue[] = [
  {
    fromFrame: 0,
    toFrame: 300,
    text: "EXAMEN captures continuous ambient audio directly from the open-source Bee wearable pendant.",
  },
  {
    fromFrame: 300,
    toFrame: 600,
    text: "At its heart lies the Semantic Gatekeeper on AWS Bedrock: an ultra-lightweight model drops over 90% of casual chatter with near-zero latency and sub-cent daily cost.",
  },
  {
    fromFrame: 600,
    toFrame: 900,
    text: "The moment it detects genuine executive signal—a promise, a physical action, or a technical topic—it routes context to LangGraph on AWS Bedrock AgentCore and synchronizes with Amazon DynamoDB.",
  },
];

export const Scene2_Architecture: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const b1 = spring({ frame: frame - 10, fps, config: { damping: 14 } });
  const b2 = spring({ frame: frame - 30, fps, config: { damping: 14 } });
  const b3 = spring({ frame: frame - 60, fps, config: { damping: 14 } });
  const b4 = spring({ frame: frame - 90, fps, config: { damping: 14 } });

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Background />
      <HeaderBar currentSection="02 / Cloud & Hardware Architecture" />

      <div
        style={{
          position: "absolute",
          top: 130,
          left: 60,
          right: 60,
          bottom: 120,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            fontSize: 44,
            fontWeight: 800,
            color: THEME.textPrimary,
            marginBottom: 12,
            letterSpacing: "-0.02em",
          }}
        >
          Zero-Shot Ingestion & Sub-Cent Intelligence
        </div>
        <div
          style={{
            fontSize: 20,
            color: THEME.textSecondary,
            marginBottom: 44,
          }}
        >
          High-throughput speech filtering on AWS Bedrock paired with continuous wearable capture
        </div>

        {/* 4 Pipeline Pillars */}
        <div
          style={{
            display: "flex",
            alignItems: "stretch",
            justifyContent: "center",
            gap: 20,
            width: "100%",
            maxWidth: 1600,
          }}
        >
          {/* Node 1: Bee Wearable */}
          <div
            style={{
              flex: 1,
              padding: "30px 24px",
              borderRadius: 20,
              backgroundColor: "rgba(17, 24, 39, 0.85)",
              border: `1px solid ${THEME.bgCardBorder}`,
              boxShadow: "0 10px 30px rgba(0,0,0,0.4)",
              transform: `scale(${b1})`,
              opacity: b1,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div style={{ fontSize: 32, marginBottom: 12 }}>🎙️</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: THEME.textPrimary, marginBottom: 8 }}>
              1. Bee Wearable
            </div>
            <div style={{ fontSize: 13, color: THEME.amazonOrange, fontWeight: 600, marginBottom: 16 }}>
              HARDWARE CAPTURE
            </div>
            <div style={{ fontSize: 14, color: THEME.textSecondary, lineHeight: 1.5, flex: 1 }}>
              Open-source pendant badge emitting a continuous real-time audio transcript stream over Server-Sent Events.
            </div>
            <div
              style={{
                marginTop: 20,
                padding: "8px 12px",
                borderRadius: 8,
                backgroundColor: "rgba(0,0,0,0.4)",
                fontFamily: "monospace",
                fontSize: 12,
                color: "#6ee7b7",
              }}
            >
              bee stream --json
            </div>
          </div>

          {/* Node 2: Semantic Gatekeeper */}
          <div
            style={{
              flex: 1.2,
              padding: "30px 24px",
              borderRadius: 20,
              backgroundColor: "rgba(17, 24, 39, 0.95)",
              border: `1px solid ${frame >= 300 ? THEME.amazonOrange : THEME.bgCardBorder}`,
              boxShadow: frame >= 300 ? `0 0 30px rgba(255, 153, 0, 0.2)` : "none",
              transform: `scale(${b2})`,
              opacity: b2,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div style={{ fontSize: 32, marginBottom: 12 }}>🛡️</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: THEME.textPrimary, marginBottom: 8 }}>
              2. Semantic Gatekeeper
            </div>
            <div style={{ fontSize: 13, color: THEME.awsBlue, fontWeight: 600, marginBottom: 16 }}>
              AWS BEDROCK (NOVA MICRO)
            </div>
            <div style={{ fontSize: 14, color: THEME.textSecondary, lineHeight: 1.5, flex: 1 }}>
              Evaluates every utterance. Drops <strong>&gt;90% of banter</strong> and chit-chat instantly.
            </div>

            {/* Split statistics */}
            <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
              <div
                style={{
                  padding: "6px 12px",
                  borderRadius: 8,
                  backgroundColor: "rgba(239, 68, 68, 0.15)",
                  color: "#fca5a5",
                  fontSize: 12,
                  fontWeight: 600,
                  display: "flex",
                  justifyContent: "space-between",
                }}
              >
                <span>90%+ Chatter</span>
                <span>Dropped (&lt;$0.01/day)</span>
              </div>
              <div
                style={{
                  padding: "6px 12px",
                  borderRadius: 8,
                  backgroundColor: "rgba(16, 185, 129, 0.15)",
                  color: "#6ee7b7",
                  fontSize: 12,
                  fontWeight: 600,
                  display: "flex",
                  justifyContent: "space-between",
                }}
              >
                <span>10% Signal</span>
                <span>Trigger Pipeline ➔</span>
              </div>
            </div>
          </div>

          {/* Node 3: LangGraph & Bedrock AgentCore */}
          <div
            style={{
              flex: 1.2,
              padding: "30px 24px",
              borderRadius: 20,
              backgroundColor: "rgba(17, 24, 39, 0.95)",
              border: `1px solid ${frame >= 600 ? THEME.awsBlue : THEME.bgCardBorder}`,
              boxShadow: frame >= 600 ? `0 0 30px rgba(0, 164, 228, 0.2)` : "none",
              transform: `scale(${b3})`,
              opacity: b3,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div style={{ fontSize: 32, marginBottom: 12 }}>⚡</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: THEME.textPrimary, marginBottom: 8 }}>
              3. AgentCore Pipeline
            </div>
            <div style={{ fontSize: 13, color: THEME.purpleAccent, fontWeight: 600, marginBottom: 16 }}>
              LANGGRAPH ORCHESTRATION
            </div>
            <div style={{ fontSize: 14, color: THEME.textSecondary, lineHeight: 1.5, flex: 1 }}>
              Specialized execution nodes on Claude 3.5 Sonnet:
              <ul style={{ paddingLeft: 18, marginTop: 6 }}>
                <li>Deep Topic Event Engine (R0-R9)</li>
                <li>Autonomous Web Search Tools</li>
                <li>Bilateral Social Commitments</li>
                <li>Action-State Verifier</li>
              </ul>
            </div>
          </div>

          {/* Node 4: DynamoDB & Serving */}
          <div
            style={{
              flex: 1,
              padding: "30px 24px",
              borderRadius: 20,
              backgroundColor: "rgba(17, 24, 39, 0.85)",
              border: `1px solid ${THEME.bgCardBorder}`,
              boxShadow: "0 10px 30px rgba(0,0,0,0.4)",
              transform: `scale(${b4})`,
              opacity: b4,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div style={{ fontSize: 32, marginBottom: 12 }}>🗄️</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: THEME.textPrimary, marginBottom: 8 }}>
              4. Cloud Storage
            </div>
            <div style={{ fontSize: 13, color: THEME.successGreen, fontWeight: 600, marginBottom: 16 }}>
              AMAZON DYNAMODB
            </div>
            <div style={{ fontSize: 14, color: THEME.textSecondary, lineHeight: 1.5, flex: 1 }}>
              Multi-table tenant isolation (`examen-user`, `examen-auth`, `examen-ops`) in `eu-central-1` with Titan V2 semantic vector search.
            </div>
            <div
              style={{
                marginTop: 20,
                padding: "8px 12px",
                borderRadius: 8,
                backgroundColor: "rgba(0,0,0,0.4)",
                fontFamily: "monospace",
                fontSize: 12,
                color: THEME.amazonOrange,
              }}
            >
              22 FastMCP Tools
            </div>
          </div>
        </div>
      </div>

      <Subtitles cues={SCENE_2_CUES} />
    </div>
  );
};
