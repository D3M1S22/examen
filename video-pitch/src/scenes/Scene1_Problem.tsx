import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { THEME } from "../constants";
import { SubtitleCue } from "../types";
import { Background } from "../components/Background";
import { HeaderBar } from "../components/HeaderBar";
import { Subtitles } from "../components/Subtitles";

export const SCENE_1_CUES: SubtitleCue[] = [
  {
    fromFrame: 0,
    toFrame: 300,
    text: "Every day, our minds are bombarded by hundreds of fleeting verbal interactions: promises made on the fly, complex technical details, and constant anxiety over everyday tasks.",
  },
  {
    fromFrame: 300,
    toFrame: 600,
    text: "Traditional voice assistants are passive and reactive: they always require an awkward wake-word and break our natural workflow.",
  },
  {
    fromFrame: 600,
    toFrame: 900,
    text: "Introducing EXAMEN: our executive second brain that listens in the background, filters out the noise, and organizes our life in real time.",
  },
];

export const Scene1_Problem: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Part 1: Problem Cards (frames 0 - 300)
  const card1Progress = spring({ frame: frame - 15, fps, config: { damping: 14 } });
  const card2Progress = spring({ frame: frame - 45, fps, config: { damping: 14 } });
  const card3Progress = spring({ frame: frame - 75, fps, config: { damping: 14 } });

  // Fade out Part 1 at frame 260-290
  const part1Opacity = interpolate(frame, [260, 290], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Part 2: Old vs New friction (frames 300 - 600)
  const part2Progress = spring({ frame: frame - 300, fps, config: { damping: 14 } });
  const part2Opacity = interpolate(frame, [290, 315, 560, 590], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Part 3: EXAMEN Brand Reveal (frames 600 - 900)
  const part3Progress = spring({ frame: frame - 600, fps, config: { damping: 12 } });
  const part3Opacity = interpolate(frame, [590, 615], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Background />
      <HeaderBar currentSection="01 / Vision & Problem" />

      {/* PART 1: The Problem Cards */}
      {frame < 300 && (
        <div
          style={{
            position: "absolute",
            top: 140,
            left: 0,
            right: 0,
            bottom: 120,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            opacity: part1Opacity,
            padding: "0 80px",
          }}
        >
          <div
            style={{
              fontSize: 48,
              fontWeight: 800,
              color: THEME.textPrimary,
              textAlign: "center",
              marginBottom: 20,
              letterSpacing: "-0.02em",
            }}
          >
            The Daily Cognitive Overload
          </div>
          <div
            style={{
              fontSize: 22,
              color: THEME.textSecondary,
              textAlign: "center",
              marginBottom: 50,
            }}
          >
            Hundreds of fleeting verbal interactions lost every single day
          </div>

          <div
            style={{
              display: "flex",
              gap: 28,
              width: "100%",
              maxWidth: 1400,
              justifyContent: "center",
            }}
          >
            {/* Card 1 */}
            <div
              style={{
                flex: 1,
                padding: "36px 30px",
                borderRadius: 20,
                backgroundColor: THEME.bgCard,
                border: `1px solid ${THEME.bgCardBorder}`,
                boxShadow: "0 20px 40px rgba(0,0,0,0.5)",
                transform: `translateY(${interpolate(card1Progress, [0, 1], [60, 0])}px) scale(${card1Progress})`,
                opacity: card1Progress,
              }}
            >
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 700,
                  color: THEME.amazonOrange,
                  marginBottom: 14,
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                }}
              >
                🤝 Relational Memory
              </div>
              <div
                style={{
                  fontSize: 26,
                  fontWeight: 700,
                  color: THEME.textPrimary,
                  marginBottom: 14,
                }}
              >
                "What did I promise Marco?"
              </div>
              <div style={{ fontSize: 16, color: THEME.textSecondary, lineHeight: 1.5 }}>
                Bilateral commitments, deadlines and follow-ups vanish in everyday banter.
              </div>
            </div>

            {/* Card 2 */}
            <div
              style={{
                flex: 1,
                padding: "36px 30px",
                borderRadius: 20,
                backgroundColor: THEME.bgCard,
                border: `1px solid ${THEME.bgCardBorder}`,
                boxShadow: "0 20px 40px rgba(0,0,0,0.5)",
                transform: `translateY(${interpolate(card2Progress, [0, 1], [60, 0])}px) scale(${card2Progress})`,
                opacity: card2Progress,
              }}
            >
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 700,
                  color: THEME.awsBlue,
                  marginBottom: 14,
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                }}
              >
                📚 Technical Discussions
              </div>
              <div
                style={{
                  fontSize: 26,
                  fontWeight: 700,
                  color: THEME.textPrimary,
                  marginBottom: 14,
                }}
              >
                "What was the sync architecture?"
              </div>
              <div style={{ fontSize: 16, color: THEME.textSecondary, lineHeight: 1.5 }}>
                Complex meeting topics discussed verbally without automatic documentation or research.
              </div>
            </div>

            {/* Card 3 */}
            <div
              style={{
                flex: 1,
                padding: "36px 30px",
                borderRadius: 20,
                backgroundColor: THEME.bgCard,
                border: `1px solid ${THEME.bgCardBorder}`,
                boxShadow: "0 20px 40px rgba(0,0,0,0.5)",
                transform: `translateY(${interpolate(card3Progress, [0, 1], [60, 0])}px) scale(${card3Progress})`,
                opacity: card3Progress,
              }}
            >
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 700,
                  color: THEME.successGreen,
                  marginBottom: 14,
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                }}
              >
                🛡️ Peace of Mind
              </div>
              <div
                style={{
                  fontSize: 26,
                  fontWeight: 700,
                  color: THEME.textPrimary,
                  marginBottom: 14,
                }}
              >
                "Did I unplug the clothes iron?"
              </div>
              <div style={{ fontSize: 16, color: THEME.textSecondary, lineHeight: 1.5 }}>
                Recurring domestic anxieties about physical actions performed on autopilot.
              </div>
            </div>
          </div>
        </div>
      )}

      {/* PART 2: Traditional Assistants vs Ambient Flow (frames 300 - 600) */}
      {frame >= 290 && frame < 600 && (
        <div
          style={{
            position: "absolute",
            top: 140,
            left: 0,
            right: 0,
            bottom: 120,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            opacity: part2Opacity,
            padding: "0 80px",
          }}
        >
          <div
            style={{
              padding: "8px 20px",
              borderRadius: 30,
              backgroundColor: "rgba(239, 68, 68, 0.15)",
              border: `1px solid rgba(239, 68, 68, 0.4)`,
              color: THEME.dangerRed,
              fontSize: 16,
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              marginBottom: 20,
            }}
          >
            The Limitation of Legacy Voice AI
          </div>

          <div
            style={{
              fontSize: 52,
              fontWeight: 800,
              color: THEME.textPrimary,
              textAlign: "center",
              marginBottom: 40,
              letterSpacing: "-0.02em",
              maxWidth: 1000,
            }}
          >
            Passive, Reactive & Wake-Word Dependent
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 40,
              width: "100%",
              maxWidth: 1100,
            }}
          >
            <div
              style={{
                flex: 1,
                padding: "36px 32px",
                borderRadius: 24,
                backgroundColor: "rgba(31, 41, 55, 0.6)",
                border: "1px dashed rgba(239, 68, 68, 0.4)",
                transform: `translateX(${interpolate(part2Progress, [0, 1], [-40, 0])}px)`,
              }}
            >
              <div style={{ fontSize: 20, fontWeight: 700, color: THEME.dangerRed, marginBottom: 12 }}>
                ❌ Traditional Voice Assistants
              </div>
              <ul style={{ color: THEME.textSecondary, fontSize: 18, lineHeight: 1.8, paddingLeft: 20 }}>
                <li>Forces you to stop what you are doing</li>
                <li>Awkward wake-words: "Hey Assistant, record this..."</li>
                <li>Zero understanding of natural conversation context</li>
                <li>Fragmented, isolated commands</li>
              </ul>
            </div>

            <div
              style={{
                fontSize: 36,
                fontWeight: 900,
                color: THEME.amazonOrange,
              }}
            >
              ➔
            </div>

            <div
              style={{
                flex: 1,
                padding: "36px 32px",
                borderRadius: 24,
                backgroundColor: "rgba(17, 24, 39, 0.9)",
                border: `1px solid ${THEME.amazonOrange}`,
                boxShadow: `0 0 30px rgba(255, 153, 0, 0.15)`,
                transform: `translateX(${interpolate(part2Progress, [0, 1], [40, 0])}px)`,
              }}
            >
              <div style={{ fontSize: 20, fontWeight: 700, color: THEME.amazonOrange, marginBottom: 12 }}>
                ✨ Ambient Intelligence
              </div>
              <ul style={{ color: THEME.textPrimary, fontSize: 18, lineHeight: 1.8, paddingLeft: 20 }}>
                <li>Always listening without friction</li>
                <li>Zero wake-words required</li>
                <li>Real-time semantic filtering of chatter</li>
                <li>Continuous executive knowledge synthesis</li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* PART 3: Reveal EXAMEN (frames 600 - 900) */}
      {frame >= 590 && (
        <div
          style={{
            position: "absolute",
            top: 140,
            left: 0,
            right: 0,
            bottom: 120,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            opacity: part3Opacity,
          }}
        >
          <div
            style={{
              width: 90,
              height: 90,
              borderRadius: "50%",
              backgroundColor: THEME.amazonOrange,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: `0 0 50px ${THEME.amazonOrange}`,
              marginBottom: 24,
              transform: `scale(${part3Progress})`,
            }}
          >
            <span style={{ fontSize: 44 }}>🐝</span>
          </div>

          <div
            style={{
              fontSize: 76,
              fontWeight: 900,
              color: THEME.textPrimary,
              letterSpacing: "-0.03em",
              marginBottom: 16,
              transform: `translateY(${interpolate(part3Progress, [0, 1], [30, 0])}px)`,
            }}
          >
            EXAMEN
          </div>

          <div
            style={{
              fontSize: 32,
              fontWeight: 600,
              color: THEME.amazonOrange,
              marginBottom: 40,
              letterSpacing: "0.02em",
            }}
          >
            Ambient Executive Intelligence
          </div>

          <div
            style={{
              display: "flex",
              gap: 20,
              transform: `translateY(${interpolate(part3Progress, [0, 1], [20, 0])}px)`,
            }}
          >
            <div
              style={{
                padding: "10px 22px",
                borderRadius: 24,
                backgroundColor: "rgba(255, 255, 255, 0.06)",
                border: "1px solid rgba(255, 255, 255, 0.12)",
                color: THEME.textPrimary,
                fontSize: 16,
                fontWeight: 600,
              }}
            >
              🐝 Bee Wearable AI Badge
            </div>
            <div
              style={{
                padding: "10px 22px",
                borderRadius: 24,
                backgroundColor: "rgba(0, 164, 228, 0.12)",
                border: `1px solid ${THEME.awsBlue}`,
                color: THEME.awsBlue,
                fontSize: 16,
                fontWeight: 600,
              }}
            >
              ☁️ AWS Bedrock & AgentCore
            </div>
            <div
              style={{
                padding: "10px 22px",
                borderRadius: 24,
                backgroundColor: "rgba(255, 153, 0, 0.12)",
                border: `1px solid ${THEME.amazonOrange}`,
                color: THEME.amazonOrange,
                fontSize: 16,
                fontWeight: 600,
              }}
            >
              🗣️ Alexa+ MCP Server
            </div>
          </div>
        </div>
      )}

      <Subtitles cues={SCENE_1_CUES} />
    </div>
  );
};
