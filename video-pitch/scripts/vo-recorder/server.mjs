#!/usr/bin/env node
// Voiceover booth for the EXAMEN v2 pitch video.
//
//   npm run vo:record          → http://localhost:4747
//
// Shows each line of src/v2/voiceover-v2.json in karaoke mode, records it from
// the microphone in the browser, lets you listen and retake, then saves it as
// public/voiceover-v2/<file>.wav (the exact name the Remotion voiceover track
// plays). Every saved take is also archived in public/voiceover-v2/takes/, so
// nothing is ever overwritten without a copy. No dependencies: Node only.

import { createServer } from "node:http";
import { existsSync, mkdirSync, readFileSync, writeFileSync, copyFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", "..");
const dataPath = join(root, "src/v2/voiceover-v2.json");
const voDir = join(root, "public/voiceover-v2");
const takesDir = join(voDir, "takes");
const statusPath = join(voDir, "recorded.json");
const PORT = Number(process.env.PORT || 4747);

const readStatus = () => {
  try {
    return JSON.parse(readFileSync(statusPath, "utf8"));
  } catch {
    return {};
  }
};

const send = (res, code, body, type = "application/json") => {
  res.writeHead(code, { "Content-Type": type, "Cache-Control": "no-store" });
  res.end(typeof body === "string" || Buffer.isBuffer(body) ? body : JSON.stringify(body));
};

const server = createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);

  if (req.method === "GET" && (url.pathname === "/" || url.pathname === "/index.html")) {
    return send(res, 200, readFileSync(join(here, "index.html")), "text/html; charset=utf-8");
  }

  if (req.method === "GET" && url.pathname === "/api/lines") {
    const data = JSON.parse(readFileSync(dataPath, "utf8"));
    return send(res, 200, { ...data, recorded: readStatus() });
  }

  // Current saved take of a line, for listening back.
  if (req.method === "GET" && url.pathname === "/api/audio") {
    const file = url.searchParams.get("file") || "";
    if (!/^[a-z0-9_]+\.wav$/.test(file)) return send(res, 400, { error: "bad file name" });
    const p = join(voDir, file);
    if (!existsSync(p)) return send(res, 404, { error: "not found" });
    return send(res, 200, readFileSync(p), "audio/wav");
  }

  if (req.method === "POST" && url.pathname === "/api/save") {
    const file = url.searchParams.get("file") || "";
    const id = url.searchParams.get("id") || "";
    if (!/^[a-z0-9_]+\.wav$/.test(file)) return send(res, 400, { error: "bad file name" });
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      const buf = Buffer.concat(chunks);
      if (buf.length < 44 || buf.toString("ascii", 0, 4) !== "RIFF") return send(res, 400, { error: "not a WAV file" });
      mkdirSync(takesDir, { recursive: true });
      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      writeFileSync(join(takesDir, file.replace(".wav", `__${stamp}.wav`)), buf);
      const target = join(voDir, file);
      if (existsSync(target) && !readStatus()[id]) {
        // keep the silent placeholder once, just in case
        const ph = join(takesDir, file.replace(".wav", "__placeholder.wav"));
        if (!existsSync(ph)) copyFileSync(target, ph);
      }
      writeFileSync(target, buf);
      const status = readStatus();
      const seconds = (buf.length - 44) / (48000 * 2);
      status[id] = { file, seconds: Math.round(seconds * 100) / 100, savedAt: new Date().toISOString() };
      writeFileSync(statusPath, JSON.stringify(status, null, 2));
      console.log(`saved ${file}  ${seconds.toFixed(2)} s`);
      send(res, 200, { ok: true, seconds, size: statSync(target).size });
    });
    return;
  }

  send(res, 404, { error: "not found" });
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`\nEXAMEN voiceover booth → http://localhost:${PORT}\n(Ctrl+C to stop)\n`);
});
