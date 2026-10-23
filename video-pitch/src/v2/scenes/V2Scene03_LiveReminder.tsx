import React from "react";
import { Video } from "@remotion/media";
import { Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { THEME } from "../../constants";
import { Background } from "../../components/Background";
import { HeaderBar } from "../../components/HeaderBar";

// NEW in v2: the live example.
// The presenter says, with no wake word:
//   "Remind me to contact Danilo and coordinate about the hackathon submission."
// Bee streams the utterance, the Gatekeeper labels it scheduled_task (+ social),
// the scheduler node writes a PlannedTask, and Daily Routines shows it.
//
// Timing (seconds from the scene start) matches lines 3.1–3.4 in voiceover-v2.json:
//   0.6  VO 3.1  "Let's try it live…"
//   5.0  LIVE 3.2 the spoken reminder (typewriter + waveform)
//   10.4 VO 3.3  pipeline steps light up, task card at 16.0
//   19.8 VO 3.4  closing banner
//
// Pass liveClipSrc (e.g. staticFile("recordings-v2/live_reminder.mp4")) to show a
// real screen/camera recording in the left panel instead of the animated mock.

export const LIVE_SENTENCE =
  "Remind me to contact Danilo and coordinate about the hackathon submission.";

const PIPELINE_STEPS: { at: number; label: string; detail: string; color: string }[] = [
  { at: 10.6, label: "Bee SSE stream", detail: "new-utterance · wearer tagged", color: THEME.amazonOrange },
  { at: 12.0, label: "Semantic Gatekeeper", detail: "labels: scheduled_task · social", color: THEME.awsBlue },
  { at: 13.6, label: "Scheduler node", detail: "PlannedTask · domain work_task", color: THEME.purpleAccent },
  { at: 15.0, label: "DynamoDB · examen-user", detail: "saved · SSE push to the dashboard", color: THEME.successGreen },
];

const Waveform: React.FC<{ active: number }> = ({ active }) => {
  const frame = useCurrentFrame();
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, height: 90 }}>
      {Array.from({ length: 28 }).map((_, i) => {
        const wobble = Math.abs(Math.sin(frame / 4 + i * 0.9) * Math.cos(frame / 9 + i * 0.4));
        return (
          <div
            key={i}
            style={{
              width: 8,
              borderRadius: 4,
              backgroundColor: THEME.amazonOrange,
              height: 8 + active * wobble * 80,
              opacity: 0.35 + active * 0.65,
            }}
          />
        );
      })}
    </div>
  );
};

export const V2Scene03_LiveReminder: React.FC<{ liveClipSrc?: string | null }> = ({ liveClipSrc = null }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const speaking = interpolate(frame, [5.0 * fps, 5.3 * fps, 9.8 * fps, 10.2 * fps], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const typed = Math.round(
    interpolate(frame, [5.2 * fps, 9.6 * fps], [0, LIVE_SENTENCE.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }),
  );
  const card = spring({ frame: frame - 16.0 * fps, fps, config: { damping: 14 } });
  const banner = spring({ frame: frame - 19.8 * fps, fps, config: { damping: 200 } });

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Background />
      <HeaderBar currentSection="03 / Live Demo · Voice to Daily Routines" />

      <div
        style={{
          position: "absolute",
          top: 120,
          left: 60,
          right: 60,
          bottom: 200,
          display: "flex",
          gap: 30,
        }}
      >
        {/* LEFT: the live capture */}
        <div
          style={{
            flex: 1.1,
            borderRadius: 20,
            backgroundColor: "rgba(17, 24, 39, 0.95)",
            border: `1px solid ${speaking > 0.5 ? THEME.amazonOrange : THEME.bgCardBorder}`,
            boxShadow: speaking > 0.5 ? "0 0 40px rgba(255, 153, 0, 0.18)" : "none",
            padding: 36,
            display: "flex",
            flexDirection: "column",
            position: "relative",
            overflow: "hidden",
            opacity: interpolate(frame, [0, 0.5 * fps], [0, 1], { extrapolateRight: "clamp" }),
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 26 }}>
            <div
              style={{
                padding: "6px 14px",
                borderRadius: 20,
                backgroundColor: "rgba(239, 68, 68, 0.15)",
                border: `1px solid ${THEME.dangerRed}`,
                color: THEME.dangerRed,
                fontSize: 15,
                fontWeight: 800,
                letterSpacing: "0.08em",
                opacity: interpolate(Math.sin(frame / 8), [-1, 1], [0.55, 1]),
              }}
            >
              ● LIVE
            </div>
            <div style={{ fontSize: 16, color: THEME.textSecondary, fontWeight: 600 }}>
              Bee wearable · no wake word · no app
            </div>
          </div>

          {liveClipSrc ? (
            <div style={{ flex: 1, borderRadius: 16, overflow: "hidden", backgroundColor: "#000" }}>
              <Video src={liveClipSrc} objectFit="cover" style={{ width: "100%", height: "100%" }} />
            </div>
          ) : (
            <>
              {/* Bee pendant with listening rings */}
              <div style={{ display: "flex", alignItems: "center", gap: 36, marginBottom: 30 }}>
                <div style={{ position: "relative", width: 150, height: 150 }}>
                  {[0, 1, 2].map((ring) => {
                    const p = ((frame + ring * 20) % 60) / 60;
                    return (
                      <div
                        key={ring}
                        style={{
                          position: "absolute",
                          inset: 0,
                          borderRadius: "50%",
                          border: `2px solid ${THEME.amazonOrange}`,
                          scale: 0.7 + p * (0.5 + speaking * 0.4),
                          opacity: (1 - p) * (0.25 + speaking * 0.6),
                        }}
                      />
                    );
                  })}
                  <div
                    style={{
                      position: "absolute",
                      inset: 30,
                      borderRadius: "50%",
                      background: "radial-gradient(circle at 35% 30%, #3b4252 0%, #111827 70%)",
                      border: `3px solid ${THEME.amazonOrange}`,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 40,
                    }}
                  >
                    🐝
                  </div>
                </div>
                <Waveform active={speaking} />
              </div>

              {/* Spoken sentence */}
              <div
                style={{
                  padding: "26px 30px",
                  borderRadius: 18,
                  backgroundColor: "rgba(255, 153, 0, 0.08)",
                  border: "1px solid rgba(255, 153, 0, 0.35)",
                  minHeight: 150,
                }}
              >
                <div
                  style={{
                    fontSize: 14,
                    fontWeight: 700,
                    color: THEME.amazonOrange,
                    letterSpacing: "0.08em",
                    marginBottom: 10,
                  }}
                >
                  🗣️ YOU, OUT LOUD
                </div>
                <div style={{ fontSize: 34, fontWeight: 700, lineHeight: 1.3, color: THEME.textPrimary }}>
                  {typed > 0 ? `“${LIVE_SENTENCE.slice(0, typed)}${typed < LIVE_SENTENCE.length ? "▍" : "”"}` : (
                    <span style={{ color: THEME.textMuted }}>listening…</span>
                  )}
                </div>
              </div>
              <div
                style={{
                  marginTop: 16,
                  fontFamily: "monospace",
                  fontSize: 15,
                  color: THEME.textMuted,
                  opacity: t > 9.8 ? 1 : 0,
                }}
              >
                bee stream --json → {"{"} "type": "new-utterance", "spoken_at": "just now" {"}"}
              </div>
            </>
          )}

          {/* Stat tiles, revealed with the task card */}
          <div style={{ display: "flex", gap: 16, marginTop: "auto", paddingTop: 20 }}>
            {[
              { big: "1", small: "sentence spoken" },
              { big: "0", small: "taps or wake words" },
              { big: "~1 s", small: "gatekeeper screening" },
            ].map((stat, i) => {
              const s = spring({ frame: frame - (16.4 + i * 0.4) * fps, fps, config: { damping: 200 } });
              return (
                <div
                  key={stat.small}
                  style={{
                    flex: 1,
                    padding: "16px 18px",
                    borderRadius: 14,
                    backgroundColor: "rgba(255,255,255,0.04)",
                    border: `1px solid ${THEME.bgCardBorder}`,
                    opacity: s,
                    translate: `0px ${interpolate(s, [0, 1], [16, 0])}px`,
                  }}
                >
                  <div style={{ fontSize: 40, fontWeight: 800, color: THEME.amazonOrange }}>{stat.big}</div>
                  <div style={{ fontSize: 15, color: THEME.textSecondary, fontWeight: 600 }}>{stat.small}</div>
                </div>
              );
            })}
          </div>
        </div>

        {/* RIGHT: pipeline + resulting task */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 18 }}>
          <div
            style={{
              borderRadius: 20,
              backgroundColor: "rgba(17, 24, 39, 0.95)",
              border: `1px solid ${THEME.bgCardBorder}`,
              padding: "24px 28px",
            }}
          >
            <div
              style={{
                fontSize: 13,
                fontWeight: 700,
                color: THEME.awsBlue,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                marginBottom: 14,
              }}
            >
              ⚡ What happens in the next few seconds
            </div>
            {PIPELINE_STEPS.map((step, i) => {
              const on = spring({ frame: frame - step.at * fps, fps, config: { damping: 200 } });
              return (
                <div
                  key={step.label}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 16,
                    padding: "10px 0",
                    borderTop: i === 0 ? "none" : `1px solid ${THEME.bgCardBorder}`,
                    opacity: 0.25 + on * 0.75,
                    translate: `${interpolate(on, [0, 1], [24, 0])}px 0px`,
                  }}
                >
                  <div
                    style={{
                      width: 34,
                      height: 34,
                      borderRadius: "50%",
                      border: `2px solid ${step.color}`,
                      backgroundColor: on > 0.5 ? step.color : "transparent",
                      color: THEME.bg,
                      fontWeight: 800,
                      fontSize: 16,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {on > 0.5 ? "✓" : i + 1}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 19, fontWeight: 700, color: THEME.textPrimary }}>{step.label}</div>
                    <div style={{ fontSize: 14, fontFamily: "monospace", color: THEME.textSecondary }}>
                      {step.detail}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Resulting Daily Routines item */}
          <div
            style={{
              borderRadius: 20,
              backgroundColor: "rgba(17, 24, 39, 0.95)",
              border: `1px solid ${card > 0.5 ? THEME.amazonOrange : THEME.bgCardBorder}`,
              boxShadow: card > 0.5 ? "0 0 35px rgba(255, 153, 0, 0.18)" : "none",
              padding: "22px 28px",
              opacity: card,
              scale: interpolate(card, [0, 1], [0.92, 1]),
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 14 }}>
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 700,
                  color: THEME.amazonOrange,
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                }}
              >
                ⏰ Daily Routines · new task
              </div>
              <div
                style={{
                  padding: "4px 12px",
                  borderRadius: 12,
                  backgroundColor: "rgba(16, 185, 129, 0.15)",
                  color: "#6ee7b7",
                  fontSize: 12,
                  fontWeight: 700,
                }}
              >
                LIVE UPDATE
              </div>
            </div>
            <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
              <div
                style={{
                  width: 26,
                  height: 26,
                  marginTop: 4,
                  borderRadius: 6,
                  border: `2px solid ${THEME.amazonOrange}`,
                  flexShrink: 0,
                }}
              />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 24, fontWeight: 800, color: THEME.textPrimary, lineHeight: 1.25 }}>
                  Contact Danilo to coordinate the hackathon submission
                </div>
                <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
                  {["WORK_TASK", "PENDING", "TODAY"].map((tag) => (
                    <span
                      key={tag}
                      style={{
                        padding: "4px 10px",
                        borderRadius: 8,
                        backgroundColor: "rgba(255,255,255,0.06)",
                        border: "1px solid rgba(255,255,255,0.12)",
                        color: THEME.textSecondary,
                        fontSize: 12,
                        fontWeight: 700,
                        letterSpacing: "0.05em",
                      }}
                    >
                      {tag}
                    </span>
                  ))}
                  <span
                    style={{
                      padding: "4px 10px",
                      borderRadius: 8,
                      backgroundColor: "rgba(0, 164, 228, 0.12)",
                      border: "1px solid rgba(0, 164, 228, 0.35)",
                      color: THEME.awsBlue,
                      fontSize: 12,
                      fontWeight: 700,
                    }}
                  >
                    👤 Danilo
                  </span>
                </div>
                <div style={{ fontSize: 14, color: THEME.textMuted, marginTop: 10 }}>
                  Source: Bee · spoken just now · “Remind me to contact Danilo…”
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Closing banner for VO 3.4 */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 130,
          display: "flex",
          justifyContent: "center",
          opacity: banner,
          translate: `0px ${interpolate(banner, [0, 1], [20, 0], { easing: Easing.out(Easing.cubic) })}px`,
        }}
      >
        <div
          style={{
            padding: "12px 30px",
            borderRadius: 30,
            backgroundColor: "rgba(255, 153, 0, 0.14)",
            border: `1px solid ${THEME.amazonOrange}`,
            color: THEME.textPrimary,
            fontSize: 22,
            fontWeight: 700,
          }}
        >
          Said once. Captured, tracked, linked to Danilo. Zero taps.
        </div>
      </div>
    </div>
  );
};
