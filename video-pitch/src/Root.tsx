import React from "react";
import { Composition, Folder } from "remotion";
import { ExamenPitchVideo } from "./ExamenPitchVideo";
import { SCENE_DURATIONS, TOTAL_DURATION } from "./constants";
import { Scene1_Problem } from "./scenes/Scene1_Problem";
import { Scene2_Architecture } from "./scenes/Scene2_Architecture";
import { Scene3_DeepTopics } from "./scenes/Scene3_DeepTopics";
import { Scene4_SocialCommitments } from "./scenes/Scene4_SocialCommitments";
import { Scene5_PeaceOfMind } from "./scenes/Scene5_PeaceOfMind";
import { Scene6_AlexaMCP } from "./scenes/Scene6_AlexaMCP";
import { Scene7_Closing } from "./scenes/Scene7_Closing";
import { ExamenPitchVideoV2, PitchV2Props } from "./v2/ExamenPitchVideoV2";
import { V2Scene03_LiveReminder } from "./v2/scenes/V2Scene03_LiveReminder";
import { V2_TOTAL_FRAMES, sceneFrames } from "./v2/timeline";
import {
  RawTake,
  V2Scene03_LiveRecorded,
  V2Scene04_TopicsRecorded,
  V2Scene05_SocialRecorded,
  V2Scene06_PeaceRecorded,
} from "./v2/scenes/V2RecordedScenes";

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

      {/* v2: same pitch + live "remind me about Danilo" example (docs/19). v1 above is unchanged. */}
      <Folder name="v2">
        <Composition
          id="ExamenPitchVideoV2"
          component={ExamenPitchVideoV2}
          durationInFrames={V2_TOTAL_FRAMES}
          fps={30}
          width={1920}
          height={1080}
          defaultProps={{ showSubtitles: true, showGuide: false, liveClipSrc: null, useRecordings: true, liveAudio: true } satisfies PitchV2Props}
        />
        {/* Same video with the teleprompter overlay, for recording the voiceover. */}
        <Composition
          id="ExamenPitchVideoV2-Guide"
          component={ExamenPitchVideoV2}
          durationInFrames={V2_TOTAL_FRAMES}
          fps={30}
          width={1920}
          height={1080}
          defaultProps={{ showSubtitles: false, showGuide: true, liveClipSrc: null, useRecordings: true, liveAudio: true } satisfies PitchV2Props}
        />
        {/* Scenes built from the real Cap recording (public/recordings-v2/cap_walkthrough_take3.mp4). */}
        <Folder name="v2-recorded">
          <Composition
            id="V2Rec03-LiveBee"
            component={V2Scene03_LiveRecorded}
            durationInFrames={sceneFrames("s03_live")}
            fps={30}
            width={1920}
            height={1080}
            defaultProps={{ liveAudio: true }}
          />
          <Composition
            id="V2Rec04-Topics"
            component={V2Scene04_TopicsRecorded}
            durationInFrames={sceneFrames("s04_topics")}
            fps={30}
            width={1920}
            height={1080}
          />
          <Composition
            id="V2Rec05-Social"
            component={V2Scene05_SocialRecorded}
            durationInFrames={sceneFrames("s05_social")}
            fps={30}
            width={1920}
            height={1080}
          />
          <Composition
            id="V2Rec06-Peace"
            component={V2Scene06_PeaceRecorded}
            durationInFrames={sceneFrames("s06_peace")}
            fps={30}
            width={1920}
            height={1080}
          />
          {/* The whole uncut take, to browse it and pick new clip times. */}
          <Composition
            id="V2Rec-RawTake3"
            component={RawTake}
            durationInFrames={216 * 30}
            fps={30}
            width={1920}
            height={1080}
          />
        </Folder>
        {/* Animated version of the live scene (used when useRecordings is false). */}
        <Folder name="v2-mockups">
          <Composition
            id="V2Scene03-LiveReminder"
            component={V2Scene03_LiveReminder}
            durationInFrames={sceneFrames("s03_live")}
            fps={30}
            width={1920}
            height={1080}
            defaultProps={{ liveClipSrc: null }}
          />
        </Folder>
      </Folder>
    </>
  );
};
