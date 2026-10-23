import React from "react";
import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import { THEME } from "../constants";
import { SubtitleCue } from "../types";
import { Background } from "../components/Background";
import { HeaderBar } from "../components/HeaderBar";
import { Subtitles } from "../components/Subtitles";

export const SCENE_6_CUES: SubtitleCue[] = [
  {
    fromFrame: 0,
    toFrame: 450,
    text: "For the Alexa+ track, EXAMEN serves a compliant FastMCP server with 22 tools over Streamable HTTP, already live on AWS. Alexa+ can naturally query your commitments, certified actions, and executive briefings directly from any Echo device.",
  },
];

export const Scene6_AlexaMCP: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const anim = spring({ frame, fps, config: { damping: 14 } });

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Background />
      <HeaderBar currentSection="06 / Alexa+ Track & FastMCP Server" />

      <div
        style={{
          position: "absolute",
          top: 120,
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
        {/* Top Badges */}
        <div style={{ display: "flex", gap: 14, marginBottom: 16 }}>
          <div
            style={{
              padding: "6px 16px",
              borderRadius: 20,
              backgroundColor: "rgba(255, 153, 0, 0.15)",
              border: `1px solid ${THEME.amazonOrange}`,
              color: THEME.amazonOrange,
              fontSize: 14,
              fontWeight: 700,
            }}
          >
            MCP SPECIFICATION 2025-11-25
          </div>
          <div
            style={{
              padding: "6px 16px",
              borderRadius: 20,
              backgroundColor: "rgba(0, 164, 228, 0.15)",
              border: `1px solid ${THEME.awsBlue}`,
              color: THEME.awsBlue,
              fontSize: 14,
              fontWeight: 700,
            }}
          >
            STREAMABLE HTTP ON AWS
          </div>
        </div>

        <div style={{ fontSize: 44, fontWeight: 800, color: THEME.textPrimary, marginBottom: 8, letterSpacing: "-0.02em" }}>
          Alexa+ FastMCP Integration: 22 Production Tools
        </div>
        <div style={{ fontSize: 18, color: THEME.textSecondary, marginBottom: 36 }}>
          Live Cloud Endpoint: <span style={{ color: THEME.amazonOrange, fontFamily: "monospace" }}>https://examen.devgiov.com/mcp</span>
        </div>

        {/* 4 Tool Clusters */}
        <div style={{ display: "flex", gap: 20, width: "100%", maxWidth: 1400, marginBottom: 32 }}>
          {/* Cluster 1 */}
          <div style={{ flex: 1, padding: 22, borderRadius: 16, backgroundColor: THEME.bgCard, border: `1px solid ${THEME.bgCardBorder}` }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: THEME.amazonOrange, marginBottom: 8 }}>
              🛡️ Actions & Verification
            </div>
            <div style={{ fontSize: 13, color: THEME.textSecondary, lineHeight: 1.6 }}>
              • query_certified_actions<br />
              • verify_action_state<br />
              • create_action & edit_action<br />
              • delete_action (2-step confirm)
            </div>
          </div>

          {/* Cluster 2 */}
          <div style={{ flex: 1, padding: 22, borderRadius: 16, backgroundColor: THEME.bgCard, border: `1px solid ${THEME.bgCardBorder}` }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: THEME.awsBlue, marginBottom: 8 }}>
              🧠 Topics & Briefings
            </div>
            <div style={{ fontSize: 13, color: THEME.textSecondary, lineHeight: 1.6 }}>
              • get_briefing_report<br />
              • search_deep_topics<br />
              • list_topic_segments<br />
              • query_topic_sources
            </div>
          </div>

          {/* Cluster 3 */}
          <div style={{ flex: 1, padding: 22, borderRadius: 16, backgroundColor: THEME.bgCard, border: `1px solid ${THEME.bgCardBorder}` }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: THEME.successGreen, marginBottom: 8 }}>
              🤝 Social & Commitments
            </div>
            <div style={{ fontSize: 13, color: THEME.textSecondary, lineHeight: 1.6 }}>
              • list_commitments (debtor/creditor)<br />
              • get_contact_dossier<br />
              • get_upcoming_tasks<br />
              • update_relationship_notes
            </div>
          </div>

          {/* Cluster 4 */}
          <div style={{ flex: 1, padding: 22, borderRadius: 16, backgroundColor: THEME.bgCard, border: `1px solid ${THEME.bgCardBorder}` }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: THEME.purpleAccent, marginBottom: 8 }}>
              🎙️ Speaker Review & Admin
            </div>
            <div style={{ fontSize: 13, color: THEME.textSecondary, lineHeight: 1.6 }}>
              • list_items_to_review<br />
              • accept_item (confirm speaker)<br />
              • dismiss_item (ignore)<br />
              • get_system_telemetry
            </div>
          </div>
        </div>

        {/* Voice Conversation Bubble */}
        <div
          style={{
            padding: "16px 28px",
            borderRadius: 30,
            backgroundColor: "rgba(255, 153, 0, 0.08)",
            border: `1px solid rgba(255, 153, 0, 0.3)`,
            display: "flex",
            alignItems: "center",
            gap: 20,
          }}
        >
          <span style={{ fontSize: 24 }}>🗣️</span>
          <span style={{ fontSize: 16, color: THEME.textPrimary }}>
            <strong>"Alexa, what commitments did I make today?"</strong> ➔ <em>"You have 1 commitment with Dario: send him the project documentation by 5:00 PM."</em>
          </span>
        </div>
      </div>

      <Subtitles cues={SCENE_6_CUES} />
    </div>
  );
};
