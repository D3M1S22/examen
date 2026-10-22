#!/usr/bin/env python3
"""Phase 0 verification spike with the physical Bee device (historical backfill, doc 06).

Captures what the real Bee stream and REST history return, then answers the open
verifications V0-V6 of docs/next_steps/historical_backfill/06_phase0_device_spike.md.

Raw captures contain personal speech: they are written to `.bee-spike/` (git-ignored).
`fixture` writes anonymised copies to `.bee-spike/fixtures/` (also git-ignored): tests must use
synthetic payloads with the real shapes instead (docs/10_bee_cli_reference.md).

Usage:
    python scripts/bee_spike.py check                         # accounts on: --user <email> or EXAMEN_CLI_USER
    python scripts/bee_spike.py capture --minutes 30          # bee stream --json + raw SSE via bee proxy
    python scripts/bee_spike.py history --hours 24            # conversations list + get <id> for each
    python scripts/bee_spike.py poll <conversation_id> --minutes 60 --until-final
    python scripts/bee_spike.py analyze                       # V0-V6 report -> <session>/analysis.md
    python scripts/bee_spike.py fixture <session>/history/conv_<id>.json <name>
    python scripts/bee_spike.py speakers                      # S1-S5 of docs/next_steps/08_speaker_identity.md

Every command accepts `--session DIR` (default: .bee-spike/<today>) so that captures
of the same day are analysed together.
"""

import argparse
import asyncio
import hashlib
import json
import re
import secrets
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
from src.core.cli import cli_tenant  # noqa: E402
from src.core.tenancy import bee_subprocess_env  # noqa: E402
from src.ingestion.stream_convo import BeeClient, get_bee_binary_path  # noqa: E402

SPIKE_ROOT = ROOT / ".bee-spike"
FIXTURE_DIR = SPIKE_ROOT / "fixtures"  # derived from personal captures: never committed


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


def bee_env() -> Optional[Dict[str, str]]:
    """The account's private Bee login (AGENTS.MD F3: every bee subprocess gets bee_subprocess_env())."""
    return bee_subprocess_env()


def run_bee_json(*sub: str, timeout: float = 60.0) -> Any:
    proc = subprocess.run(bee_cmd(*sub, "--json"), capture_output=True, text=True, timeout=timeout, env=bee_env())
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
    print(subprocess.run(bee_cmd("--version"), capture_output=True, text=True, env=bee_env()).stdout.strip())
    status = subprocess.run(bee_cmd("status"), capture_output=True, text=True, env=bee_env())
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
                                                stderr=asyncio.subprocess.STDOUT, limit=10 * 1024 * 1024,
                                                env=bee_env())
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


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _capture_raw_sse(out_raw: Path, out_events: Path, port: int, types: Optional[str],
                           stop: asyncio.Event) -> None:
    """Ground truth: raw SSE frames (event names, comment pings) through `bee proxy`."""
    import httpx

    port = port or _free_port()  # 8787 is often taken by a running EXAMEN server's own proxy
    proxy = await asyncio.create_subprocess_exec(*bee_cmd("proxy", "--port", str(port), "--idle-timeout", "255"),
                                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                                                 env=bee_env())
    try:
        said: List[str] = []
        while True:
            line = (await asyncio.wait_for(proxy.stdout.readline(), timeout=15)).decode()
            if not line:
                raise RuntimeError(f"bee proxy exited before listening on port {port}: "
                                   + (" | ".join(said[-5:]) or "no output"))
            said.append(line.strip())
            if "Proxy listening" in line:
                break
        url = f"http://127.0.0.1:{port}/v1/stream" + (f"?types={types}" if types else "")
        current: Dict[str, Any] = {}
        async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
            async with client.stream("GET", url, headers={"Accept": "text/event-stream"}) as response:
                print(f"{datetime.now():%H:%M:%S} [sse] HTTP {response.status_code}")
                # No wait_for around the iterator: cancelling __anext__ closes the httpx stream
                async for line in response.aiter_lines():
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
                    elif line.startswith("retry:"):
                        continue
                    elif ":" in line:
                        field, value = line.split(":", 1)
                        value = value[1:] if value.startswith(" ") else value
                        current[field] = current[field] + "\n" + value if field == "data" and field in current else value
                print(f"{datetime.now():%H:%M:%S} [sse] stream ended by the server")
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
        # One failed source (e.g. the proxy) must not end the capture of the other one
        deadline = time.monotonic() + args.minutes * 60
        running = set(tasks)
        while running and time.monotonic() < deadline:
            done, running = await asyncio.wait(running, timeout=deadline - time.monotonic(),
                                               return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task.exception():
                    print(f"capture task failed (the other source keeps recording): {task.exception()!r}")
    finally:
        stop.set()
        _, pending = await asyncio.wait(tasks, timeout=3)
        for task in pending:
            task.cancel()
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
    (out / ("history_summary.json" if order else "history_summary_ids.json")).write_text(json.dumps(report, indent=2, ensure_ascii=False))
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
    client = BeeClient(transport="cli")
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
        # Completed conversations only return the final transcription (new ids): match its text then
        pool = [r for r in rest_rt if r["realtime"]] or list(rest_rt)
        if conv_uuid in uuid_to_conv:
            uuid_ok += 1
            pool = [r for r in pool if r["conv"] is uuid_to_conv[conv_uuid]] or pool
        live_id = utt.get("id") or p.get("id")
        best = next((r for r in rest_rt if live_id is not None and str(r["u"].get("id")) == str(live_id)), None)
        kind = "id"
        if best is None:
            best = next((r for r in pool if r["norm"] == text), None)
            kind = "exact"
        if best is None and pool:
            best = max(pool, key=lambda r: token_jaccard(r["norm"], text))
            kind = "fuzzy" if token_jaccard(best["norm"], text) >= 0.6 else None
        if best is None or not kind:
            matches.append({"text": text[:60], "matched": False})
            continue
        u = best["u"]
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
    live_lags = []
    for item in live:
        spoken_live = (item["payload"].get("utterance") or {}).get("spoken_at")
        if spoken_live:
            try:
                ts = datetime.fromisoformat(str(spoken_live).replace("Z", "+00:00")).timestamp() * 1000
            except ValueError:
                ts = epoch_ms(spoken_live)
            if ts:
                live_lags.append((item["received_at_ms"] - ts) / 1000)
    report["V5"] = {"received_minus_live_spoken_at_s": stats(live_lags),
                    "received_minus_rest_spoken_at_s": stats(lags_spoken), "received_minus_end_s": stats(lags_end)}
    md += ["## V2 — Live utterance id vs REST realtime utterance id",
           f"- Live utterances: {len(live)}, matched in REST realtime: {report['V2']['matched']}, "
           f"id equal: {id_equal}, conversation_uuid resolved via REST uuid: {uuid_ok}", "",
           "## V5 — Lag live receipt vs REST times (seconds)",
           f"- received − live `utterance.spoken_at`: {report['V5']['received_minus_live_spoken_at_s']}",
           f"- received − REST spoken_at: {report['V5']['received_minus_rest_spoken_at_s']}",
           f"- received − end: {report['V5']['received_minus_end_s']}",
           "- Suggested `BACKFILL_MATCH_WINDOW_SECONDS`: max lag + margin", ""]

    # V3: list ordering
    summary_path = hist / "history_summary.json"  # written by a listing run (not --ids)
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


def _stream_payloads(cap: Path) -> List[Dict[str, Any]]:
    """(received_at_ms, payload) of every typed event, from the raw SSE capture or `bee stream --json`."""
    out: List[Dict[str, Any]] = []
    for e in read_jsonl(cap / "sse_events.jsonl"):
        if isinstance(e.get("data"), dict):
            out.append({"ms": e["received_at_ms"], "type": e["data"].get("type") or e.get("event"), "data": e["data"]})
    if out:
        return out
    for rec in read_jsonl(cap / "stream_json.jsonl"):
        try:
            data = json.loads(rec["line"])
        except (json.JSONDecodeError, KeyError):
            continue
        if isinstance(data, dict):
            out.append({"ms": rec["received_at_ms"], "type": data.get("type"), "data": data})
    return out


def cmd_speakers(args) -> None:
    """Speaker identity verification (doc 08 §7): tags vs `bee me`, lag, matching, REST speakers.

    Prints ids, first names, scores and timings only, never utterance text."""
    from src.ingestion.bee_identity import WearerIdentity

    sess = session_dir(args)
    events = _stream_payloads(sess / "capture")
    me = run_bee_json("me")
    utter_ms: Dict[str, int] = {}
    tags: List[Dict[str, Any]] = []
    for e in events:
        if e["type"] == "new-utterance" and isinstance(e["data"].get("utterance"), dict):
            utter_ms.setdefault(str(e["data"]["utterance"].get("id")), e["ms"])
        elif e["type"] == "tagged-utterance":
            tags.append(e)
    lags = [(t["ms"] - utter_ms[str(t["data"].get("utterance_id"))]) / 1000.0
            for t in tags if str(t["data"].get("utterance_id")) in utter_ms]
    people: Dict[str, Dict[str, Any]] = {}
    for t in tags:
        d = t["data"]
        entry = people.setdefault(str(d.get("person_id")), {"names": Counter(), "scores": [], "conversations": set()})
        entry["names"][d.get("person_first_name") or ""] += 1
        if isinstance(d.get("speaker_score"), (int, float)):
            entry["scores"].append(float(d["speaker_score"]))
        entry["conversations"].add(d.get("conversation_uuid"))
    who = WearerIdentity(first_name="")
    who.apply_profile(me)
    roles = Counter(who.match_tag(t["data"].get("person_id"), t["data"].get("person_first_name"),
                                  t["data"].get("speaker_score")).role for t in tags)
    rest_keys: Counter = Counter()
    rest_speakers: Counter = Counter()
    for path in sorted((sess / "history").glob("conv_*.json")):
        detail = json.loads(path.read_text())
        conv = detail.get("conversation") if isinstance(detail.get("conversation"), dict) else detail
        for tx in conv.get("transcriptions") or []:
            for utt in tx.get("utterances") or []:
                rest_keys.update(k for k in utt if "speak" in k or "person" in k)
                rest_speakers[str(utt.get("speaker"))] += 1

    def stats(values: List[float]) -> str:
        if not values:
            return "n/a"
        return f"min {min(values):.2f} · median {statistics.median(values):.2f} · max {max(values):.2f} (n={len(values)})"

    lines = [f"# Speaker identity check — {sess.name}", "",
             f"- bee me: id={me.get('id')} first_name={me.get('first_name')!r}",
             f"- utterances: {len(utter_ms)}, tagged: {len(tags)} "
             f"({100.0 * len(tags) / len(utter_ms):.0f} %)" if utter_ms else "- utterances: 0",
             "", "## S1–S3 person ids"]
    for pid, entry in people.items():
        lines.append(f"- person_id={pid}: names={dict(entry['names'])}, tags={sum(entry['names'].values())}, "
                     f"score {stats(entry['scores'])}, conversations={len(entry['conversations'])}, "
                     f"equals bee me id: {pid == str(me.get('id'))}")
    lines += ["", f"- EXAMEN matching over the capture: {dict(roles)}; wearer ids bound: {sorted(who.person_ids)}",
              "", "## S4 tag lag after its utterance (s)", f"- {stats(lags)}",
              f"- within the {1.5:.1f} s default wait: {sum(1 for x in lags if x <= 1.5)}/{len(lags)}",
              "", "## S5 REST history speaker fields",
              f"- utterance keys about speakers: {dict(rest_keys)}",
              f"- speaker values: {dict(rest_speakers.most_common(8))}"]
    report = "\n".join(lines)
    (sess / "speakers.md").write_text(report + "\n")
    print(report)
    print(f"\nSaved {sess / 'speakers.md'}")


def cmd_fixture(args) -> None:
    detail = json.loads(Path(args.source).read_text())
    conv = detail.get("conversation") if isinstance(detail.get("conversation"), dict) else detail
    salt = secrets.token_hex(16)  # never stored: tokens cannot be reversed with a dictionary
    people: Dict[str, str] = {}
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
    for t in conv.get("transcriptions") or []:
        for u in t.get("utterances") or []:
            speaker = u.get("speaker")
            if speaker and speaker != "Unknown" and not str(speaker).startswith("speaker_"):
                u["speaker"] = people.setdefault(speaker, f"person_{len(people) + 1}")
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
    parser.add_argument("--user", help="EXAMEN account whose paired Bee to use (default: $EXAMEN_CLI_USER); "
                                       "not needed with AUTH_ENABLED=false (host bee login)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Binary, login, account and latest conversations")

    p = sub.add_parser("capture", help="Record bee stream --json and the raw SSE stream")
    p.add_argument("--minutes", type=float, default=30)
    p.add_argument("--types", help="Comma-separated event types (default: server default, like EXAMEN)")
    p.add_argument("--port", type=int, default=0, help="Local port for bee proxy (default: a free port)")
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
    sub.add_parser("speakers", help="Speaker identity check (doc 08 §7): tags vs bee me, lag, REST speakers")

    p = sub.add_parser("fixture", help="Anonymise a conversation detail into .bee-spike/fixtures/")
    p.add_argument("source")
    p.add_argument("name")
    p.add_argument("--keep-text", action="store_true", help="Do not redact utterance text")

    for name in ("check", "capture", "history", "poll", "analyze", "fixture", "speakers"):
        sub.choices[name].add_argument("--session", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    args = parser.parse_args()
    with cli_tenant(getattr(args, "user", None)):
        _dispatch(args)


def _dispatch(args) -> None:
    {"check": cmd_check, "capture": cmd_capture, "history": cmd_history, "poll": cmd_poll,
     "analyze": cmd_analyze, "fixture": cmd_fixture, "speakers": cmd_speakers}[args.command](args)


if __name__ == "__main__":
    main()
