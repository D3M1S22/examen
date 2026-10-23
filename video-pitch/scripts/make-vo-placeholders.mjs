#!/usr/bin/env node
// Creates silent WAV placeholders for every v2 voiceover line, so the Remotion
// timeline shows where each line is spoken before anything is recorded.
//
//   npm run vo:placeholders            # create missing files only (never touches recorded takes)
//   npm run vo:placeholders -- --force # overwrite everything with silence
//
// Source of truth: src/v2/voiceover-v2.json. Output: public/voiceover-v2/.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const data = JSON.parse(readFileSync(join(root, "src/v2/voiceover-v2.json"), "utf8"));
const force = process.argv.includes("--force");
const SAMPLE_RATE = 16000;

const silentWav = (seconds) => {
  const samples = Math.round(seconds * SAMPLE_RATE);
  const dataBytes = samples * 2; // mono, 16-bit
  const buf = Buffer.alloc(44 + dataBytes);
  buf.write("RIFF", 0);
  buf.writeUInt32LE(36 + dataBytes, 4);
  buf.write("WAVE", 8);
  buf.write("fmt ", 12);
  buf.writeUInt32LE(16, 16);
  buf.writeUInt16LE(1, 20); // PCM
  buf.writeUInt16LE(1, 22); // mono
  buf.writeUInt32LE(SAMPLE_RATE, 24);
  buf.writeUInt32LE(SAMPLE_RATE * 2, 28);
  buf.writeUInt16LE(2, 32);
  buf.writeUInt16LE(16, 34);
  buf.write("data", 36);
  buf.writeUInt32LE(dataBytes, 40);
  return buf;
};

const write = (rel, seconds) => {
  const out = join(root, "public", rel);
  mkdirSync(dirname(out), { recursive: true });
  if (existsSync(out) && !force) {
    console.log(`keep    ${rel}`);
    return;
  }
  writeFileSync(out, silentWav(seconds));
  console.log(`silent  ${rel}  (${seconds}s)`);
};

for (const line of data.lines) {
  write(line.file, line.duration);
}
write("voiceover-v2/music_bed.wav", data.totalSeconds);
console.log(`\n${data.lines.length} lines, total video ${data.totalSeconds}s`);
