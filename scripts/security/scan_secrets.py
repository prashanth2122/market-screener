from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    excerpt: str


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    allow_paths = {
        ".env.example",
        ".pre-commit-config.yaml",
    }

    tracked_files = _git_ls_files(repo_root)
    findings: list[Finding] = []
    for rel in tracked_files:
        if rel in allow_paths:
            continue
        if _is_binaryish(rel):
            continue
        path = repo_root / rel
        try:
            if not path.is_file():
                continue
            if path.stat().st_size > 1_000_000:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for match in _iter_findings(text):
            findings.append(
                Finding(
                    path=rel,
                    line=match[0],
                    kind=match[1],
                    excerpt=match[2],
                )
            )

    if findings:
        payload = {
            "status": "fail",
            "finding_count": len(findings),
            "findings": [finding.__dict__ for finding in findings[:200]],
            "note": "Review findings; move real secrets to .env and rotate leaked credentials.",
        }
        print(json.dumps(payload, indent=2))
        return 2

    print(json.dumps({"status": "ok", "finding_count": 0}, indent=2))
    return 0


def _git_ls_files(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _is_binaryish(path: str) -> bool:
    lower = path.lower()
    for ext in (
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".zip",
        ".gz",
        ".tgz",
        ".7z",
        ".exe",
        ".dll",
        ".pyd",
        ".so",
        ".dylib",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".mp4",
        ".mov",
        ".avi",
        ".sqlite",
        ".db",
    ):
        if lower.endswith(ext):
            return True
    return False


def _iter_findings(text: str):
    patterns: list[tuple[str, re.Pattern[str]]] = [
        ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----")),
        ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        ("github_token", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
        ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
        ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
        ("telegram_bot_token", re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")),
        ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
        (
            "generic_secret_assignment",
            re.compile(
                r"(?i)\b(api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*['\"][^'\"\r\n]{12,}['\"]"
            ),
        ),
    ]

    for idx, line in enumerate(text.splitlines(), start=1):
        if _looks_like_dummy_secret(line):
            continue
        for kind, pattern in patterns:
            if pattern.search(line):
                excerpt = line.strip()
                if len(excerpt) > 240:
                    excerpt = excerpt[:240] + "...(truncated)"
                yield (idx, kind, excerpt)


def _looks_like_dummy_secret(line: str) -> bool:
    lowered = line.lower()
    # Common fixtures / placeholders we intentionally keep in tests and examples.
    for token in (
        "demo-",
        "dummy-",
        "example-",
        "changeme",
        "change_me",
        "smtp-password",
        "test-password",
        "test-secret",
        "replace_with",
        "***redacted***",
    ):
        if token in lowered:
            return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
