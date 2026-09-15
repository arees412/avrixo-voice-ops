"""Small offline secret-pattern scan scoped to Avrixo-authored files."""

from __future__ import annotations

import re
from pathlib import Path

PATTERNS = {
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9]{40,}\b"),
}


def main() -> None:
    package_root = Path(__file__).parents[1]
    repo_root = package_root.parent
    roots = (package_root, repo_root / "docs", repo_root / ".github" / "workflows")
    files = [repo_root / "README.md", repo_root / "UPSTREAM.md", repo_root / "FORK_CHANGES.md"]
    for root in roots:
        if root.exists():
            files.extend(path for path in root.rglob("*") if path.is_file())
    findings: list[str] = []
    scanned: set[Path] = set()
    for path in set(files):
        if any(
            part in {".venv", "__pycache__", ".mypy_cache", ".pytest_cache"} for part in path.parts
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        scanned.add(path)
        for name, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{path.relative_to(repo_root)}: {name}")
    if findings:
        raise SystemExit("potential secrets found:\n" + "\n".join(findings))
    print(f"Secret scan passed: {len(scanned)} files checked")


if __name__ == "__main__":
    main()
