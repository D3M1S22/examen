import React from "react";
import { Composition } from "remotion";
import { ExamenPitchVideo } from "./ExamenPitchVideo";
import { SCENE_DURATIONS, TOTAL_DURATION } from "./constants";
import { Scene1_Problem } from "./scenes/Scene1_Problem";
import { Scene2_Architecture } from "./scenes/Scene2_Architecture";
import { Scene3_DeepTopics } from "./scenes/Scene3_DeepTopics";
import { Scene4_SocialCommitments } from "./scenes/Scene4_SocialCommitments";
import { Scene5_PeaceOfMind } from "./scenes/Scene5_PeaceOfMind";
import { Scene6_AlexaMCP } from "./scenes/Scene6_AlexaMCP";
import { Scene7_Closing } from "./scenes/Scene7_Closing";

export const RemotionRoot: React.FC = () => {
  // 6 transitions of 15 frames overlap = 90 frames reduction
  const fullVideoDuration = TOTAL_DURATION - 6 * 15; // 5310 frames = 177s (2m 57s)

  return (
    <>
      {/* Main Full 3-Minute Video Pitch */}
      <Composition
        id="ExamenPitchVideo"
        component={ExamenPitchVideo}
        durationInFrames={fullVideoDuration}
        fps={30}
        width={1920}
        height={1080}
      />

      {/* Individual Scene Compositions for Focused Editing & Preview */}
      <Composition
        id="Scene1-Problem"
        component={Scene1_Problem}
        durationInFrames={SCENE_DURATIONS.SCENE_1_PROBLEM}
        fps={30}
        width={1920}
        height={1080}
      />

      <Composition
        id="Scene2-Architecture"
        component={Scene2_Architecture}
        durationInFrames={SCENE_DURATIONS.SCENE_2_ARCHITECTURE}
        fps={30}
        width={1920}
        height={1080}
      />

      <Composition
        id="Scene3-DeepTopics"
        component={Scene3_DeepTopics}
        durationInFrames={SCENE_DURATIONS.SCENE_3_TOPICS}
        fps={30}
        width={1920}
        height={1080}
      />

      <Composition
        id="Scene4-SocialCommitments"
        component={Scene4_SocialCommitments}
        durationInFrames={SCENE_DURATIONS.SCENE_4_SOCIAL}
        fps={30}
        width={1920}
        height={1080}
      />

      <Composition
        id="Scene5-PeaceOfMind"
        component={Scene5_PeaceOfMind}
        durationInFrames={SCENE_DURATIONS.SCENE_5_PEACE_OF_MIND}
        fps={30}
        width={1920}
        height={1080}
      />

      <Composition
        id="Scene6-AlexaMCP"
        component={Scene6_AlexaMCP}
        durationInFrames={SCENE_DURATIONS.SCENE_6_ALEXA_MCP}
        fps={30}
        width={1920}
        height={1080}
      />

      <Composition
        id="Scene7-Closing"
        component={Scene7_Closing}
        durationInFrames={SCENE_DURATIONS.SCENE_7_CLOSING}
        fps={30}
        width={1920}
        height={1080}
      />
    </>
  );
};
