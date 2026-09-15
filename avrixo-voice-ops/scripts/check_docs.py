"""Validate required fork documentation, local links, and Mermaid fences."""

from __future__ import annotations

import re
from pathlib import Path


def main() -> None:
    package_root = Path(__file__).parents[1]
    repo_root = package_root.parent
    required = (
        repo_root / "README.md",
        repo_root / "UPSTREAM.md",
        repo_root / "FORK_CHANGES.md",
        repo_root / "docs" / "architecture.md",
        repo_root / "docs" / "security.md",
        repo_root / "docs" / "development.md",
    )
    missing = [str(path.relative_to(repo_root)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit(f"missing required documentation: {', '.join(missing)}")

    failures: list[str] = []
    mermaid_blocks = 0
    link_pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    mermaid_pattern = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
    mermaid_directives = (
        "flowchart",
        "stateDiagram",
        "sequenceDiagram",
        "classDiagram",
        "erDiagram",
        "gantt",
        "timeline",
    )
    for document in required:
        text = document.read_text(encoding="utf-8")
        blocks = mermaid_pattern.findall(text)
        mermaid_blocks += len(blocks)
        if text.count("```mermaid") != len(blocks):
            failures.append(f"{document.name}: malformed Mermaid fence")
        for block in blocks:
            first_line = block.strip().splitlines()[0] if block.strip() else ""
            if not first_line.startswith(mermaid_directives):
                failures.append(f"{document.name}: unknown Mermaid directive {first_line!r}")
        for target in link_pattern.findall(text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            clean_target = target.split("#", 1)[0]
            if clean_target and not (document.parent / clean_target).resolve().exists():
                failures.append(f"{document.name}: missing link target {target}")
    if failures:
        raise SystemExit("\n".join(failures))
    if mermaid_blocks < 3:
        raise SystemExit("expected at least three Mermaid diagrams")
    print(
        f"Documentation validation passed: {len(required)} documents, "
        f"{mermaid_blocks} Mermaid diagrams"
    )


if __name__ == "__main__":
    main()
