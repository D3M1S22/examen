export const FPS = 30;

// Scene Durations in Frames (30 fps)
// Total: 3 minutes = 180s = 5400 frames
export const SCENE_DURATIONS = {
  SCENE_1_PROBLEM: 30 * FPS, // 900 frames (0:00 - 0:30)
  SCENE_2_ARCHITECTURE: 30 * FPS, // 900 frames (0:30 - 1:00)
  SCENE_3_TOPICS: 35 * FPS, // 1050 frames (1:00 - 1:35)
  SCENE_4_SOCIAL: 30 * FPS, // 900 frames (1:35 - 2:05)
  SCENE_5_PEACE_OF_MIND: 25 * FPS, // 750 frames (2:05 - 2:30)
  SCENE_6_ALEXA_MCP: 15 * FPS, // 450 frames (2:30 - 2:45)
  SCENE_7_CLOSING: 15 * FPS, // 450 frames (2:45 - 3:00)
};

export const TOTAL_DURATION =
  SCENE_DURATIONS.SCENE_1_PROBLEM +
  SCENE_DURATIONS.SCENE_2_ARCHITECTURE +
  SCENE_DURATIONS.SCENE_3_TOPICS +
  SCENE_DURATIONS.SCENE_4_SOCIAL +
  SCENE_DURATIONS.SCENE_5_PEACE_OF_MIND +
  SCENE_DURATIONS.SCENE_6_ALEXA_MCP +
  SCENE_DURATIONS.SCENE_7_CLOSING; // 5400 frames

export const THEME = {
  bg: "#080c14",
  bgCard: "#111827",
  bgCardBorder: "#1f2937",
  textPrimary: "#f9fafb",
  textSecondary: "#9ca3af",
  textMuted: "#6b7280",
  amazonOrange: "#ff9900",
  awsNavy: "#141f2e",
  awsBlue: "#00a4e4",
  successGreen: "#10b981",
  dangerRed: "#ef4444",
  purpleAccent: "#a855f7",
};

