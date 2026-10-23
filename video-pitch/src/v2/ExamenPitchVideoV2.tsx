import React from "react";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { Subtitles } from "../components/Subtitles";
import { SubtitleCue } from "../types";
import { PLACED_LINES, V2_TRANSITION_FRAMES, sceneFrames } from "./timeline";
import { VoiceoverTrack } from "./components/VoiceoverTrack";
import { VoGuide } from "./components/VoGuide";
import { V2Scene01_Problem } from "./scenes/V2Scene01_Problem";
import { V2Scene02_Architecture } from "./scenes/V2Scene02_Architecture";
import { V2Scene03_LiveReminder } from "./scenes/V2Scene03_LiveReminder";
import { V2Scene04_DeepTopics } from "./scenes/V2Scene04_DeepTopics";
import { V2Scene05_Social } from "./scenes/V2Scene05_Social";
import { V2Scene06_PeaceOfMind } from "./scenes/V2Scene06_PeaceOfMind";
import { V2Scene07_AlexaMCP } from "./scenes/V2Scene07_AlexaMCP";
import { V2Scene08_Closing } from "./scenes/V2Scene08_Closing";
import {
  V2Scene03_LiveRecorded,
  V2Scene04_TopicsRecorded,
  V2Scene05_SocialRecorded,
  V2Scene06_PeaceRecorded,
} from "./scenes/V2RecordedScenes";

// EXAMEN pitch v2: v1 storyboard (shorter slots) + the live "remind me about
// Danilo" example as scene 03. Script and timings:
// docs/19_video_pitch_v2_script_live_demo.md. The v1 video (ExamenPitchVideo)
// is unchanged.

export type PitchV2Props = {
  showSubtitles: boolean;
  showGuide: boolean;
  /** e.g. staticFile("recordings-v2/live_reminder.mp4"); null = animated mock. */
  liveClipSrc: string | null;
  /** Scenes 03–06 from the real Cap recording (true) or the animated mockups (false). */
  useRecordings: boolean;
  /** Keep the presenter's microphone audio of the live Bee line in scene 03. */
  liveAudio: boolean;
};

const SUBTITLE_CUES: SubtitleCue[] = PLACED_LINES.map((l) => ({
  fromFrame: l.fromFrame,
  toFrame: l.fromFrame + l.plannedFrames,
  text: l.kind === "live" ? `🔴 “${l.text}”` : l.text,
}));

const SCENES: { key: string; render: (p: PitchV2Props) => React.ReactNode }[] = [
  { key: "s01_problem", render: () => <V2Scene01_Problem /> },
  { key: "s02_architecture", render: () => <V2Scene02_Architecture /> },
  {
    key: "s03_live",
    render: (p) =>
      p.useRecordings ? (
        <V2Scene03_LiveRecorded liveAudio={p.liveAudio} />
      ) : (
        <V2Scene03_LiveReminder liveClipSrc={p.liveClipSrc} />
      ),
  },
  { key: "s04_topics", render: (p) => (p.useRecordings ? <V2Scene04_TopicsRecorded /> : <V2Scene04_DeepTopics />) },
  { key: "s05_social", render: (p) => (p.useRecordings ? <V2Scene05_SocialRecorded /> : <V2Scene05_Social />) },
  { key: "s06_peace", render: (p) => (p.useRecordings ? <V2Scene06_PeaceRecorded /> : <V2Scene06_PeaceOfMind />) },
  { key: "s07_alexa", render: () => <V2Scene07_AlexaMCP /> },
  { key: "s08_closing", render: () => <V2Scene08_Closing /> },
];

export const ExamenPitchVideoV2: React.FC<PitchV2Props> = (props) => {
  return (
    <div style={{ position: "relative", width: "100%", height: "100%", backgroundColor: "#080c14" }}>
      <TransitionSeries>
        {SCENES.flatMap((scene, i) => {
          const items = [
            <TransitionSeries.Sequence key={scene.key} name={scene.key} durationInFrames={sceneFrames(scene.key)}>
              {scene.render(props)}
            </TransitionSeries.Sequence>,
          ];
          if (i < SCENES.length - 1) {
            items.push(
              <TransitionSeries.Transition
                key={`${scene.key}-fade`}
                presentation={fade()}
                timing={linearTiming({ durationInFrames: V2_TRANSITION_FRAMES })}
              />,
            );
          }
          return items;
        })}
      </TransitionSeries>

      <VoiceoverTrack />
      {props.showSubtitles ? <Subtitles cues={SUBTITLE_CUES} /> : null}
      {props.showGuide ? <VoGuide /> : null}
    </div>
  );
};
