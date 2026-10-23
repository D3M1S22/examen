// v2 copy of src/scenes/Scene6_AlexaMCP.tsx (v1 stays untouched).
// Subtitles come from the global voiceover track (src/v2/voiceover-v2.json).
import React from "react";
import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import { THEME } from "../../constants";
import { Background } from "../../components/Background";
import { HeaderBar } from "../../components/HeaderBar";

export const V2Scene07_AlexaMCP: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const anim = spring({ frame, fps, config: { damping: 14 } });

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Background />
      <HeaderBar currentSection="07 / Alexa+ Track & FastMCP Server" />

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
              🛡️ Actions & Routines
            </div>
            <div style={{ fontSize: 13, color: THEME.textSecondary, lineHeight: 1.6 }}>
              • verify_action_status<br />
              • get_daily_actions_recap<br />
              • create_planned_task<br />
              • get_upcoming_tasks
            </div>
          </div>

          {/* Cluster 2 */}
          <div style={{ flex: 1, padding: 22, borderRadius: 16, backgroundColor: THEME.bgCard, border: `1px solid ${THEME.bgCardBorder}` }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: THEME.awsBlue, marginBottom: 8 }}>
              🧠 Topics & Briefings
            </div>
            <div style={{ fontSize: 13, color: THEME.textSecondary, lineHeight: 1.6 }}>
              • get_topic_briefing<br />
              • get_session_dossier<br />
              • list_session_dossiers<br />
              • get_live_event_outline
            </div>
          </div>

          {/* Cluster 3 */}
          <div style={{ flex: 1, padding: 22, borderRadius: 16, backgroundColor: THEME.bgCard, border: `1px solid ${THEME.bgCardBorder}` }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: THEME.successGreen, marginBottom: 8 }}>
              🤝 Social & Commitments
            </div>
            <div style={{ fontSize: 13, color: THEME.textSecondary, lineHeight: 1.6 }}>
              • get_social_commitments<br />
              • query_social_contact<br />
              • get_contact_profile<br />
              • update_contact
            </div>
          </div>

          {/* Cluster 4 */}
          <div style={{ flex: 1, padding: 22, borderRadius: 16, backgroundColor: THEME.bgCard, border: `1px solid ${THEME.bgCardBorder}` }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: THEME.purpleAccent, marginBottom: 8 }}>
              🎙️ Speaker Review & Curation
            </div>
            <div style={{ fontSize: 13, color: THEME.textSecondary, lineHeight: 1.6 }}>
              • list_items_to_review<br />
              • accept_item (confirm speaker)<br />
              • dismiss_item (ignore)<br />
              • update_* / delete_* (2-step)
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
            <strong>"Alexa, what's on my plate today?"</strong> ➔ <em>"Two things: contact Danilo to coordinate the hackathon submission, and send Dario the repo docs by 5 PM."</em>
            <span style={{ marginLeft: 14, fontSize: 12, fontFamily: "monospace", color: THEME.textMuted }}>
              tool: get_upcoming_tasks · simulated Alexa+ conversation
            </span>
          </span>
        </div>
      </div>
    </div>
  );
};
