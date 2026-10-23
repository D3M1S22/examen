import React from "react";
import { Audio } from "@remotion/media";
import { Sequence, staticFile } from "remotion";
import { PLACED_LINES, V2_TOTAL_FRAMES } from "../timeline";

// One audio clip per voiceover line, placed at its planned time.
// The files in public/voiceover-v2/ start as silent placeholders
// (npm run vo:placeholders). Record each line, export it as WAV with the
// same file name, and it drops into place: the Studio timeline shows every
// clip by its line id. A take may run longer than planned, up to the start
// of the next line.

export const VoiceoverTrack: React.FC = () => {
  return (
    <>
      {PLACED_LINES.map((line) => (
        <Sequence
          key={line.id}
          name={`${line.kind === "live" ? "LIVE" : "VO"} ${line.id} · ${line.duration}s`}
          from={line.fromFrame}
          durationInFrames={line.slotFrames}
          layout="none"
        >
          <Audio src={staticFile(line.file)} />
        </Sequence>
      ))}

      {/* Background music bed: silent placeholder, keep it licensed (hackathon rule). */}
      <Sequence name="Music bed (placeholder)" durationInFrames={V2_TOTAL_FRAMES} layout="none">
        <Audio src={staticFile("voiceover-v2/music_bed.wav")} volume={0.12} />
      </Sequence>
    </>
  );
};
