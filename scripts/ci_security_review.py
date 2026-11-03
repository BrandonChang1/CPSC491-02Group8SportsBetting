"""CI-only, conservative check for tracked secret files and obvious credentials.

Outputs paths and rule names, never matched lines or values.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

FORBIDDEN_NAMES = {".env", "id_rsa", "id_ed25519", "credentials.json", "service-account.json"}
FORBIDDEN_SUFFIXES = (".pem", ".p12", ".pfx", ".key")
PATTERNS = {
    "private key marker": re.compile(rb"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
    "GitHub token": re.compile(rb"\b(?:ghp_|gho_|ghu_|ghs_|ghr_)[A-Za-z0-9]{20,}\b"),
    "GitHub fine-grained token": re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    "AWS access key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
}


def main() -> int:
    tracked = subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0")
    findings = []
    for raw in tracked:
        if not raw:
            continue
        path = Path(raw.decode("utf-8", errors="surrogateescape"))
        name = path.name.lower()
        if name in FORBIDDEN_NAMES or name.startswith(".env.") and name != ".env.example" or name.endswith(FORBIDDEN_SUFFIXES):
            findings.append((str(path), "sensitive filename"))
            continue
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue
        for label, regex in PATTERNS.items():
            if regex.search(data):
                findings.append((str(path), label))
    if findings:
        print(f"Secret scan: FAIL ({len(findings)} potential issue(s)).")
        for path, label in findings:
            print(f"  {path}: {label} (content intentionally omitted)")
        return 1
    print(f"Secret scan: PASS ({len(tracked) - (1 if tracked and not tracked[-1] else 0)} tracked paths checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
