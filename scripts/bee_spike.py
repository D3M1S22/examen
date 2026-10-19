#!/usr/bin/env python3
"""Phase 0 verification spike with the physical Bee device (historical backfill, doc 06).

Captures what the real Bee stream and REST history return, then answers the open
verifications V0-V6 of docs/next_steps/historical_backfill/06_phase0_device_spike.md.

Raw captures contain personal speech: they are written to `.bee-spike/` (git-ignored).
Only `fixture` writes into the repository, and it redacts text by default.

Usage:
    python scripts/bee_spike.py check
    python scripts/bee_spike.py capture --minutes 30          # bee stream --json + raw SSE via bee proxy
    python scripts/bee_spike.py history --hours 24            # conversations list + get <id> for each
    python scripts/bee_spike.py poll <conversation_id> --minutes 60 --until-final
    python scripts/bee_spike.py analyze                       # V0-V6 report -> <session>/analysis.md
    python scripts/bee_spike.py fixture <session>/history/conv_<id>.json <name>

Every command accepts `--session DIR` (default: .bee-spike/<today>) so that captures
of the same day are analysed together.
"""

import argparse
import asyncio
import hashlib
import json
import re
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ingestion.bee_history import epoch_ms  # noqa: E402
from src.ingestion.coverage import normalize_text, token_jaccard  # noqa: E402
from src.ingestion.stream_convo import BeeClient, get_bee_binary_path  # noqa: E402

SPIKE_ROOT = ROOT / ".bee-spike"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "bee_history"


def now_ms() -> int:
    return int(time.time() * 1000)


def iso(ms: Optional[int]) -> str:
    return datetime.fromtimestamp(ms / 1000).isoformat(timespec="seconds") if ms else "-"


def session_dir(args) -> Path:
    path = Path(args.session) if args.session else SPIKE_ROOT / datetime.now().strftime("%Y-%m-%d")
    path.mkdir(parents=True, exist_ok=True)
    return path


def bee_cmd(*sub: str) -> List[str]:
    binary = get_bee_binary_path()
    if not binary:
        sys.exit("bee binary not found: see 06_phase0_device_spike.md §1")
    return BeeClient()._build_cmd(list(sub))


def run_bee_json(*sub: str, timeout: float = 60.0) -> Any:
    proc = subprocess.run(bee_cmd(*sub, "--json"), capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"bee {' '.join(sub)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return json.loads(proc.stdout)


def append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def stats(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"n": 0}
    return {"n": len(values), "min": round(min(values), 1), "median": round(statistics.median(values), 1),
            "max": round(max(values), 1)}


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

def cmd_check(args) -> None:
    binary = get_bee_binary_path()
    print(f"bee binary : {binary or 'NOT FOUND'}")
    if not binary:
        sys.exit(1)
    print(subprocess.run(bee_cmd("--version"), capture_output=True, text=True).stdout.strip())
    status = subprocess.run(bee_cmd("status"), capture_output=True, text=True)
    print(status.stdout.strip() or status.stderr.strip())
    if "Not logged in" in status.stdout:
        sys.exit("Not logged in: run `bee login` (or `bee login --qr`) and approve it in the Bee app.")
    me = run_bee_json("me")
    print(f"account    : {me.get('first_name', '')} {me.get('last_name', '')} (id {me.get('id')})")
    listing = run_bee_json("conversations", "list", "--limit", "3")
    for conv in listing.get("conversations") or []:
        print(f"recent conv: {conv.get('id')} state={conv.get('state')} start={iso(epoch_ms(conv.get('start_time')))} "
              f"end={iso(epoch_ms(conv.get('end_time')))}")
    print(f"session dir: {session_dir(args)}")


# ---------------------------------------------------------------------------
# capture
# ---------------------------------------------------------------------------

async def _capture_stream_json(out: Path, types: Optional[str], stop: asyncio.Event) -> None:
    """What EXAMEN consumes today: `bee stream --json` lines, stamped on receipt."""
    sub = ["stream", "--json"] + (["--types", types] if types else [])
    proc = await asyncio.create_subprocess_exec(*bee_cmd(*sub), stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.STDOUT, limit=10 * 1024 * 1024)
    try:
        while not stop.is_set():
            try:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            if not raw:
                print(f"{datetime.now():%H:%M:%S} [json] stream ended (exit {await proc.wait()})")
                break
            line = raw.decode("utf-8", "replace").rstrip("\n")
            append_jsonl(out, {"received_at_ms": now_ms(), "line": line})
            try:
                data = json.loads(line)
                shape = sorted(data.keys()) if isinstance(data, dict) else type(data).__name__
            except json.JSONDecodeError:
                shape = f"non-json: {line[:80]}"
            print(f"{datetime.now():%H:%M:%S} [json] {shape}")
    finally:
        if proc.returncode is None:
            proc.terminate()
            await proc.wait()


async def _capture_raw_sse(out_raw: Path, out_events: Path, port: int, types: Optional[str],
                           stop: asyncio.Event) -> None:
    """Ground truth: raw SSE frames (event names, comment pings) through `bee proxy`."""
    import httpx

    proxy = await asyncio.create_subprocess_exec(*bee_cmd("proxy", "--port", str(port), "--idle-timeout", "0"),
                                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        while True:
            line = (await asyncio.wait_for(proxy.stdout.readline(), timeout=15)).decode()
            if not line:
                raise RuntimeError("bee proxy exited before listening")
            if "Proxy listening" in line:
                break
        url = f"http://127.0.0.1:{port}/v1/stream" + (f"?types={types}" if types else "")
        current: Dict[str, Any] = {}
        async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
            async with client.stream("GET", url, headers={"Accept": "text/event-stream"}) as response:
                print(f"{datetime.now():%H:%M:%S} [sse] HTTP {response.status_code}")
                lines = response.aiter_lines()
                while not stop.is_set():
                    try:
                        line = await asyncio.wait_for(lines.__anext__(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    except StopAsyncIteration:
                        print(f"{datetime.now():%H:%M:%S} [sse] stream ended")
                        break
                    received = now_ms()
                    append_jsonl(out_raw, {"received_at_ms": received, "raw": line})
                    if line.startswith(":"):
                        append_jsonl(out_events, {"received_at_ms": received, "event": "<comment>", "data": line})
                    elif line == "":
                        if current:
                            data = current.get("data")
                            try:
                                data = json.loads(data) if data is not None else None
                            except json.JSONDecodeError:
                                pass
                            append_jsonl(out_events, {"received_at_ms": received, "event": current.get("event"),
                                                      "id": current.get("id"), "data": data})
                            text = ((data or {}).get("utterance") or {}).get("text") if isinstance(data, dict) else None
                            print(f"{datetime.now():%H:%M:%S} [sse] {current.get('event')} {(text or '')[:70]}")
                        current = {}
                    elif ":" in line:
                        field, value = line.split(":", 1)
                        value = value[1:] if value.startswith(" ") else value
                        current[field] = current[field] + "\n" + value if field == "data" and field in current else value
    finally:
        if proxy.returncode is None:
            proxy.terminate()
            await proxy.wait()


async def _capture(args) -> None:
    out = session_dir(args) / "capture"
    out.mkdir(exist_ok=True)
    stop = asyncio.Event()
    tasks = []
    if not args.no_json:
        tasks.append(asyncio.create_task(_capture_stream_json(out / "stream_json.jsonl", args.types, stop)))
    if not args.no_raw:
        tasks.append(asyncio.create_task(
            _capture_raw_sse(out / "sse_raw.jsonl", out / "sse_events.jsonl", args.port, args.types, stop)))
    print(f"Capturing into {out} for {args.minutes} min (Ctrl+C to stop early)...")
    try:
        done, _ = await asyncio.wait(tasks, timeout=args.minutes * 60, return_when=asyncio.FIRST_EXCEPTION)
        for task in done:
            if task.exception():
                print(f"capture task failed: {task.exception()!r}")
    finally:
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)
    print(f"Done. Next: python scripts/bee_spike.py history --hours 2 --session {out.parent}")


def cmd_capture(args) -> None:
    try:
        asyncio.run(_capture(args))
    except KeyboardInterrupt:
        print("Interrupted.")


# ---------------------------------------------------------------------------
# history & poll
# ---------------------------------------------------------------------------

def _summarise_conv(detail: Dict[str, Any]) -> Dict[str, Any]:
    conv = detail.get("conversation") if isinstance(detail.get("conversation"), dict) else detail
    txs = [{"id": t.get("id"), "realtime": t.get("realtime"), "utterances": len(t.get("utterances") or [])}
           for t in conv.get("transcriptions") or []]
    return {"id": conv.get("id"), "uuid": conv.get("uuid") or conv.get("conversation_uuid"),
            "state": conv.get("state"), "start": iso(epoch_ms(conv.get("start_time"))),
            "end": iso(epoch_ms(conv.get("end_time"))), "transcriptions": txs,
            "conversation_keys": sorted(conv.keys()), "top_keys": sorted(detail.keys())}


def cmd_history(args) -> None:
    out = session_dir(args) / "history"
    out.mkdir(exist_ok=True)
    since = now_ms() - int(args.hours * 3_600_000)
    ids: List[int] = [int(i) for i in args.ids.split(",")] if args.ids else []
    order: List[Dict[str, Any]] = []
    if not ids:
        cursor, page = None, 0
        while page < args.max_pages:
            sub = ["conversations", "list", "--limit", "100"] + (["--cursor", cursor] if cursor else [])
            payload = run_bee_json(*sub)
            (out / f"list_page_{page}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
            items = payload.get("conversations") or []
            for item in items:
                start = epoch_ms(item.get("start_time"))
                order.append({"id": item.get("id"), "start_ms": start, "created_ms": epoch_ms(item.get("created_at"))})
                if start is None or start >= since or (epoch_ms(item.get("end_time")) or now_ms()) >= since:
                    ids.append(int(item["id"]))
            cursor, page = payload.get("next_cursor"), page + 1
            oldest = min((o["start_ms"] for o in order if o["start_ms"]), default=None)
            if not cursor or not items or (oldest is not None and oldest < since):
                break
    summaries = []
    for conv_id in ids:
        detail = run_bee_json("conversations", "get", str(conv_id))
        (out / f"conv_{conv_id}.json").write_text(json.dumps(detail, indent=2, ensure_ascii=False))
        summary = _summarise_conv(detail)
        summaries.append(summary)
        print(f"{summary['id']:>8} uuid={'yes' if summary['uuid'] else 'NO '} state={summary['state']!s:<10} "
              f"{summary['start']} -> {summary['end']} tx={summary['transcriptions']}")

    def monotonic(key: str) -> Optional[bool]:
        values = [o[key] for o in order if o[key] is not None]
        return all(a >= b for a, b in zip(values, values[1:])) if len(values) > 1 else None

    report = {"fetched_at": iso(now_ms()), "hours": args.hours, "conversations": summaries,
              "list_order": {"start_time_desc": monotonic("start_ms"), "created_at_desc": monotonic("created_ms"),
                             "first_ids": [o["id"] for o in order[:10]]}}
    (out / "history_summary.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n{len(summaries)} conversations saved in {out}")
    print(f"list ordering: newest-first by start_time={report['list_order']['start_time_desc']} "
          f"by created_at={report['list_order']['created_at_desc']}")


def cmd_poll(args) -> None:
    out = session_dir(args) / "history" / f"poll_{args.id}.jsonl"
    out.parent.mkdir(exist_ok=True)
    deadline = time.time() + args.minutes * 60
    last = None
    while time.time() < deadline:
        try:
            detail = run_bee_json("conversations", "get", str(args.id))
        except Exception as e:  # transient API errors must not stop a long poll
            print(f"{datetime.now():%H:%M:%S} error: {e}")
            time.sleep(args.interval)
            continue
        s = _summarise_conv(detail)
        snapshot = {"t_ms": now_ms(), "state": s["state"], "end": s["end"], "transcriptions": s["transcriptions"]}
        append_jsonl(out, snapshot)
        key = json.dumps({k: snapshot[k] for k in ("state", "end", "transcriptions")})
        if key != last:
            print(f"{datetime.now():%H:%M:%S} state={s['state']} end={s['end']} tx={s['transcriptions']}")
            last = key
        has_final = any(t["realtime"] is False and t["utterances"] for t in s["transcriptions"])
        if args.until_final and has_final and str(s["state"]).lower() != "processing":
            (out.parent / f"conv_{args.id}.json").write_text(json.dumps(detail, indent=2, ensure_ascii=False))
            print("Final transcription present: stopping.")
            return
        time.sleep(args.interval)


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------

async def _run_production_parser(lines: List[str]) -> Counter:
    """Feeds captured `bee stream --json` lines through BeeClient.stream_events (production parsing)."""
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        f.write("\n".join(lines) + "\n")
        path = f.name
    client = BeeClient()
    client._build_cmd = lambda _sub: ["cat", path]
    counts: Counter = Counter()
    async for event in client.stream_events():
        if event["event"] == "stream-disconnected":
            break
        counts[event["event"]] += 1
    client.stop()
    Path(path).unlink(missing_ok=True)
    return counts


def _live_utterances(sse_events: List[Dict[str, Any]], json_lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from_sse = [{"received_at_ms": e["received_at_ms"], "payload": e["data"]} for e in sse_events
                if e["event"] == "new-utterance" and isinstance(e["data"], dict)]
    from_json = []
    for rec in json_lines:
        try:
            data = json.loads(rec["line"])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("utterance"), dict):
            from_json.append({"received_at_ms": rec["received_at_ms"], "payload": data})
    # The two captures can differ (one connection may be dropped): use the more complete one
    return from_sse if len(from_sse) > len(from_json) else from_json


def cmd_analyze(args) -> None:
    sess = session_dir(args)
    cap, hist = sess / "capture", sess / "history"
    json_lines = read_jsonl(cap / "stream_json.jsonl")
    sse_events = read_jsonl(cap / "sse_events.jsonl")
    convs = {}
    for path in sorted(hist.glob("conv_*.json")):
        detail = json.loads(path.read_text())
        conv = detail.get("conversation") if isinstance(detail.get("conversation"), dict) else detail
        convs[conv["id"]] = conv
    report: Dict[str, Any] = {"session": str(sess), "generated_at": iso(now_ms())}
    md: List[str] = [f"# Bee spike analysis — {sess.name}", ""]

    # V0: does production parsing recognise utterances from `bee stream --json`?
    decoded = []  # (record, parsed payload or None), aligned with json_lines
    for rec in json_lines:
        try:
            decoded.append((rec, json.loads(rec["line"])))
        except json.JSONDecodeError:
            decoded.append((rec, None))
    parsed_json = [d for _, d in decoded if d is not None]
    shapes = Counter(",".join(sorted(d.keys())) if isinstance(d, dict) else type(d).__name__ for d in parsed_json)
    with_type = sum(1 for d in parsed_json if isinstance(d, dict) and (d.get("type") or d.get("event")))
    prod = asyncio.run(_run_production_parser([r["line"] for r in json_lines])) if json_lines else Counter()
    sse_counts = Counter(e["event"] for e in sse_events)
    report["V0"] = {"json_lines": len(json_lines), "json_lines_with_type_field": with_type,
                    "json_shapes": dict(shapes.most_common(15)), "production_parser_events": dict(prod),
                    "sse_event_counts": dict(sse_counts)}
    utterance_lines = sum(1 for d in parsed_json if isinstance(d, dict) and isinstance(d.get("utterance"), dict))
    on_wire = max(sse_counts.get("new-utterance", 0), utterance_lines)
    v0_alert = on_wire > 0 and prod.get("new-utterance", 0) < on_wire
    report["V0"]["utterances_on_wire"] = on_wire
    md += ["## V0 — Live parsing of `bee stream --json`",
           f"- JSON lines: {len(json_lines)}, with a `type`/`event` field: {with_type}",
           f"- Production `BeeClient.stream_events` yields: {dict(prod)}",
           f"- Raw SSE event counts (proxy): {dict(sse_counts)}",
           "- Payload shapes (`bee stream --json`): " + "; ".join(f"`{k}` ×{v}" for k, v in shapes.most_common(10)),
           f"- Utterances on the wire: {on_wire}, recognised as `new-utterance`: {prod.get('new-utterance', 0)}",
           f"- **{'ALERT: utterances on the wire are NOT recognised by BeeClient' if v0_alert else 'OK / not enough data'}**",
           ""]

    # Payload schema per SSE event type (first sample saved for docs/fixtures)
    samples_dir = sess / "samples"
    samples_dir.mkdir(exist_ok=True)
    keys_by_event: Dict[str, set] = defaultdict(set)
    for e in sse_events:
        if isinstance(e["data"], dict):
            name = e["event"] or "<none>"
            keys_by_event[name] |= set(e["data"].keys())
            for k, v in e["data"].items():
                if isinstance(v, dict):
                    keys_by_event[name] |= {f"{k}.{kk}" for kk in v}
            sample = samples_dir / f"{name}.json"
            if not sample.exists():
                sample.write_text(json.dumps(e["data"], indent=2, ensure_ascii=False))
    report["event_schemas"] = {k: sorted(v) for k, v in keys_by_event.items()}
    md += ["## SSE payload schemas", *[f"- `{k}`: {', '.join(sorted(v))}" for k, v in keys_by_event.items()], ""]

    # V1: uuid in REST detail
    with_uuid = [cid for cid, c in convs.items() if c.get("uuid") or c.get("conversation_uuid")]
    report["V1"] = {"conversations": len(convs), "with_uuid": len(with_uuid)}
    md += ["## V1 — `uuid` in `GET /v1/conversations/{id}`",
           f"- {len(with_uuid)}/{len(convs)} conversation details carry a uuid", ""]

    # V2 / V5: match live utterances against the REST realtime transcription
    uuid_to_conv = {(c.get("uuid") or c.get("conversation_uuid")): c for c in convs.values()
                    if c.get("uuid") or c.get("conversation_uuid")}
    rest_rt = []
    for c in convs.values():
        for t in c.get("transcriptions") or []:
            for u in t.get("utterances") or []:
                rest_rt.append({"conv": c, "realtime": bool(t.get("realtime")), "u": u,
                                "norm": normalize_text(u.get("text") or "")})
    matches, lags_spoken, lags_end, id_equal, uuid_ok = [], [], [], 0, 0
    live = _live_utterances(sse_events, json_lines)
    for item in live:
        p = item["payload"]
        utt = p.get("utterance") or {}
        text = normalize_text(utt.get("text") or p.get("text") or "")
        conv_uuid = p.get("conversation_uuid") or p.get("conversation_id")
        pool = [r for r in rest_rt if r["realtime"]]
        if conv_uuid in uuid_to_conv:
            uuid_ok += 1
            pool = [r for r in pool if r["conv"] is uuid_to_conv[conv_uuid]] or pool
        best = next((r for r in pool if r["norm"] == text), None)
        kind = "exact"
        if best is None and pool:
            best = max(pool, key=lambda r: token_jaccard(r["norm"], text))
            kind = "fuzzy" if token_jaccard(best["norm"], text) >= 0.6 else None
        if not kind:
            matches.append({"text": text[:60], "matched": False})
            continue
        u = best["u"]
        live_id = utt.get("id") or p.get("id")
        if live_id is not None and str(live_id) == str(u.get("id")):
            id_equal += 1
        spoken, end = epoch_ms(u.get("spoken_at") or u.get("start")), epoch_ms(u.get("end"))
        if spoken:
            lags_spoken.append((item["received_at_ms"] - spoken) / 1000)
        if end:
            lags_end.append((item["received_at_ms"] - end) / 1000)
        matches.append({"text": text[:60], "matched": kind, "live_id": live_id, "rest_id": u.get("id"),
                        "conv_id": best["conv"].get("id")})
    report["V2"] = {"live_utterances": len(live), "matched": sum(1 for m in matches if m["matched"]),
                    "live_id_equals_rest_realtime_id": id_equal, "conversation_uuid_resolved": uuid_ok,
                    "samples": matches[:20]}
    report["V5"] = {"received_minus_spoken_s": stats(lags_spoken), "received_minus_end_s": stats(lags_end)}
    md += ["## V2 — Live utterance id vs REST realtime utterance id",
           f"- Live utterances: {len(live)}, matched in REST realtime: {report['V2']['matched']}, "
           f"id equal: {id_equal}, conversation_uuid resolved via REST uuid: {uuid_ok}", "",
           "## V5 — Lag live receipt vs REST times (seconds)",
           f"- received − spoken_at: {report['V5']['received_minus_spoken_s']}",
           f"- received − end: {report['V5']['received_minus_end_s']}",
           "- Suggested `BACKFILL_MATCH_WINDOW_SECONDS`: max lag + margin", ""]

    # V3: list ordering
    summary_path = hist / "history_summary.json"
    order = json.loads(summary_path.read_text())["list_order"] if summary_path.exists() else {}
    report["V3"] = order
    md += ["## V3 — `GET /v1/conversations` ordering", f"- {order or 'no history capture'}",
           "- `from` semantics need the proxy transport (not exposed by the CLI list command)", ""]

    # V4: state transitions from poll files
    v4 = {}
    for path in sorted(hist.glob("poll_*.jsonl")):
        snaps = read_jsonl(path)
        transitions, prev = [], None
        for s in snaps:
            sig = (s["state"], s["end"], json.dumps(s["transcriptions"]))
            if sig != prev:
                transitions.append({"at": iso(s["t_ms"]), "state": s["state"], "end": s["end"],
                                    "transcriptions": s["transcriptions"]})
                prev = sig
        v4[path.stem.replace("poll_", "")] = transitions
    report["V4"] = v4
    md += ["## V4 — Conversation states & final transcription timing"]
    for cid, transitions in v4.items():
        md.append(f"- conversation {cid}:")
        md += [f"  - {t['at']} state={t['state']} end={t['end']} tx={t['transcriptions']}" for t in transitions]
    md.append(f"- States seen in history: {sorted({str(c.get('state')) for c in convs.values()})}")
    md.append("")

    # V6: heartbeat cadence
    comment_ts = [e["received_at_ms"] for e in sse_events if e["event"] == "<comment>"]
    hb_ts = [r["received_at_ms"] for r, d in decoded
             if isinstance(d, dict) and "timestamp" in d and not (d.get("type") or d.get("event"))]
    gaps = lambda ts: [(b - a) / 1000 for a, b in zip(ts, ts[1:])]  # noqa: E731
    report["V6"] = {"sse_comment_interval_s": stats(gaps(comment_ts)),
                    "json_timestamp_heartbeat_interval_s": stats(gaps(hb_ts))}
    md += ["## V6 — Heartbeat cadence (seconds)",
           f"- SSE comment pings: {report['V6']['sse_comment_interval_s']}",
           f"- `{{\"timestamp\": …}}` lines in `--json`: {report['V6']['json_timestamp_heartbeat_interval_s']}",
           "- The live read timeout is 330 s (`stream_convo.py`): it must stay well above the max interval", ""]

    (sess / "analysis.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    (sess / "analysis.md").write_text("\n".join(md))
    print("\n".join(md))
    print(f"Saved {sess / 'analysis.md'} and analysis.json; payload samples in {samples_dir}")


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _redact_words(text: str, salt: str) -> str:
    # Same word -> same token everywhere, so realtime/final transcriptions still match after redaction
    return _WORD_RE.sub(lambda m: "w" + hashlib.sha1((salt + m.group(0).lower()).encode()).hexdigest()[:6], text)


def cmd_fixture(args) -> None:
    detail = json.loads(Path(args.source).read_text())
    conv = detail.get("conversation") if isinstance(detail.get("conversation"), dict) else detail
    salt = hashlib.sha1(str(conv.get("id")).encode()).hexdigest()
    for key in ("title", "short_summary", "summary"):
        if conv.get(key):
            conv[key] = f"[redacted {key}]"
    if isinstance(conv.get("primary_location"), dict):
        conv["primary_location"].update({"address": "[redacted address]", "latitude": 45.0703, "longitude": 7.6869})
        conv["primary_location"].pop("name", None)
    if not args.keep_text:
        for t in conv.get("transcriptions") or []:
            for u in t.get("utterances") or []:
                u["text"] = _redact_words(u.get("text") or "", salt)
    leftovers = sorted(k for k, v in conv.items() if isinstance(v, str)
                       and k not in {"uuid", "state", "device_type", "title", "short_summary", "summary"})
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    target = FIXTURE_DIR / f"{args.name}.json"
    target.write_text(json.dumps(detail, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {target.relative_to(ROOT)}")
    if leftovers:
        print(f"Review these string fields before committing: {leftovers}")


# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", help="Capture directory (default: .bee-spike/<today>)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Binary, login, account and latest conversations")

    p = sub.add_parser("capture", help="Record bee stream --json and the raw SSE stream")
    p.add_argument("--minutes", type=float, default=30)
    p.add_argument("--types", help="Comma-separated event types (default: server default, like EXAMEN)")
    p.add_argument("--port", type=int, default=8787, help="Local port for bee proxy")
    p.add_argument("--no-raw", action="store_true", help="Skip the raw SSE capture through bee proxy")
    p.add_argument("--no-json", action="store_true", help="Skip `bee stream --json` (single raw SSE connection)")

    p = sub.add_parser("history", help="Fetch conversation list + details of the last N hours")
    p.add_argument("--hours", type=float, default=24)
    p.add_argument("--ids", help="Comma-separated conversation ids (skips listing)")
    p.add_argument("--max-pages", type=int, default=10)

    p = sub.add_parser("poll", help="Poll one conversation until its final transcription appears")
    p.add_argument("id", type=int)
    p.add_argument("--minutes", type=float, default=60)
    p.add_argument("--interval", type=float, default=60)
    p.add_argument("--until-final", action="store_true")

    sub.add_parser("analyze", help="Answer V0-V6 from the session captures")

    p = sub.add_parser("fixture", help="Anonymise a conversation detail into tests/fixtures/bee_history/")
    p.add_argument("source")
    p.add_argument("name")
    p.add_argument("--keep-text", action="store_true", help="Do not redact utterance text")

    for name in ("check", "capture", "history", "poll", "analyze", "fixture"):
        sub.choices[name].add_argument("--session", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    args = parser.parse_args()
    {"check": cmd_check, "capture": cmd_capture, "history": cmd_history, "poll": cmd_poll,
     "analyze": cmd_analyze, "fixture": cmd_fixture}[args.command](args)


if __name__ == "__main__":
    main()
