import React from "react";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { SCENE_DURATIONS } from "./constants";
import { Scene1_Problem } from "./scenes/Scene1_Problem";
import { Scene2_Architecture } from "./scenes/Scene2_Architecture";
import { Scene3_DeepTopics } from "./scenes/Scene3_DeepTopics";
import { Scene4_SocialCommitments } from "./scenes/Scene4_SocialCommitments";
import { Scene5_PeaceOfMind } from "./scenes/Scene5_PeaceOfMind";
import { Scene6_AlexaMCP } from "./scenes/Scene6_AlexaMCP";
import { Scene7_Closing } from "./scenes/Scene7_Closing";

export const ExamenPitchVideo: React.FC = () => {
  const transitionDuration = 15; // 0.5s crossfade between scenes

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", backgroundColor: "#080c14" }}>
      <TransitionSeries>
        {/* Scene 1: Problem & Vision (30s) */}
        <TransitionSeries.Sequence durationInFrames={SCENE_DURATIONS.SCENE_1_PROBLEM}>
          <Scene1_Problem />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 2: Hardware & Cloud Architecture (30s) */}
        <TransitionSeries.Sequence durationInFrames={SCENE_DURATIONS.SCENE_2_ARCHITECTURE}>
          <Scene2_Architecture />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 3: Live Demo 1 - Deep Topics & Echo Show View (35s) */}
        <TransitionSeries.Sequence durationInFrames={SCENE_DURATIONS.SCENE_3_TOPICS}>
          <Scene3_DeepTopics />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 4: Live Demo 2 - Social Rolodex & Bilateral Promises (30s) */}
        <TransitionSeries.Sequence durationInFrames={SCENE_DURATIONS.SCENE_4_SOCIAL}>
          <Scene4_SocialCommitments />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 5: Live Demo 3 - Peace of Mind & Speaker Review (25s) */}
        <TransitionSeries.Sequence durationInFrames={SCENE_DURATIONS.SCENE_5_PEACE_OF_MIND}>
          <Scene5_PeaceOfMind />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 6: Alexa+ FastMCP 22 Tools (15s) */}
        <TransitionSeries.Sequence durationInFrames={SCENE_DURATIONS.SCENE_6_ALEXA_MCP}>
          <Scene6_AlexaMCP />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 7: Closing & Impact (15s) */}
        <TransitionSeries.Sequence durationInFrames={SCENE_DURATIONS.SCENE_7_CLOSING}>
          <Scene7_Closing />
        </TransitionSeries.Sequence>
      </TransitionSeries>
    </div>
  );
};

