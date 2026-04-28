from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LatencyStats:
    count: int
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    max_ms: float | None


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze reliability soak JSONL logs.")
    parser.add_argument("logfile", type=Path, help="Path to soak_*.jsonl")
    parser.add_argument("--out", type=Path, default=None, help="Optional output markdown path")
    args = parser.parse_args()

    events = _read_jsonl(args.logfile)
    checks = [event for event in events if event.get("kind") == "http_check"]
    summaries = [event for event in events if event.get("kind") == "summary"]

    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for check in checks:
        name = str(check.get("name") or "unknown")
        by_name[name].append(check)

    lines: list[str] = []
    lines.append(f"# Soak Report: {args.logfile.name}")
    lines.append("")
    if summaries:
        summary = summaries[-1]
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- duration_minutes: {summary.get('duration_minutes')}")
        lines.append(f"- interval_seconds: {summary.get('interval_seconds')}")
        lines.append(f"- total_iterations: {summary.get('total_iterations')}")
        lines.append(f"- request_ok: {summary.get('request_ok')}")
        lines.append(f"- request_fail: {summary.get('request_fail')}")
        lines.append("")

    lines.append("## Endpoint Breakdown")
    lines.append("")

    overall_ok = 0
    overall_fail = 0
    for name in sorted(by_name.keys()):
        entries = by_name[name]
        ok_count = sum(1 for e in entries if bool(e.get("ok")) is True)
        fail_count = len(entries) - ok_count
        overall_ok += ok_count
        overall_fail += fail_count
        status_counts = Counter()
        error_counts = Counter()
        durations = []
        for e in entries:
            status = e.get("status")
            if status is not None:
                status_counts[int(status)] += 1
            err = e.get("error")
            if err:
                error_counts[str(err)[:120]] += 1
            dur = e.get("duration_ms")
            if isinstance(dur, (int, float)):
                durations.append(float(dur))

        stats = _latency_stats(durations)
        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"- checks: {len(entries)} ok={ok_count} fail={fail_count}")
        if stats.count:
            lines.append(
                f"- latency_ms: p50={_fmt(stats.p50_ms)} p95={_fmt(stats.p95_ms)} p99={_fmt(stats.p99_ms)} max={_fmt(stats.max_ms)}"
            )
        if status_counts:
            top_status = ", ".join(f"{k}:{v}" for k, v in status_counts.most_common(6))
            lines.append(f"- status: {top_status}")
        if error_counts:
            top_errors = ", ".join(f"{k} ({v})" for k, v in error_counts.most_common(3))
            lines.append(f"- errors: {top_errors}")
        lines.append("")

    lines.append("## Overall")
    lines.append("")
    total = overall_ok + overall_fail
    fail_rate = (overall_fail / total) if total else 0.0
    lines.append(f"- total_checks: {total}")
    lines.append(f"- ok: {overall_ok}")
    lines.append(f"- fail: {overall_fail}")
    lines.append(f"- fail_rate: {fail_rate:.4f}")
    lines.append("")

    report = "\n".join(lines)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
    else:
        print(report)

    return 0


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            data.append(obj)
    return data


def _percentile(sorted_values: list[float], p: float) -> float | None:
    if not sorted_values:
        return None
    if p <= 0:
        return sorted_values[0]
    if p >= 1:
        return sorted_values[-1]
    k = (len(sorted_values) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    d0 = sorted_values[f] * (c - k)
    d1 = sorted_values[c] * (k - f)
    return d0 + d1


def _latency_stats(durations: list[float]) -> LatencyStats:
    durations = [d for d in durations if d >= 0]
    durations.sort()
    return LatencyStats(
        count=len(durations),
        p50_ms=_percentile(durations, 0.50),
        p95_ms=_percentile(durations, 0.95),
        p99_ms=_percentile(durations, 0.99),
        max_ms=(durations[-1] if durations else None),
    )


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}"


if __name__ == "__main__":
    raise SystemExit(main())
