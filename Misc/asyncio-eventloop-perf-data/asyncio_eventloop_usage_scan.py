from __future__ import annotations

import json
from pathlib import Path
import re


PATTERNS = {
    "asyncio_import": re.compile(r"\b(?:from\s+asyncio\s+import|import\s+asyncio)\b"),
    "call_soon": re.compile(r"\bcall_soon(?:_threadsafe)?\b"),
    "call_later": re.compile(r"\bcall_later\b"),
    "call_at": re.compile(r"\bcall_at\b"),
    "create_task": re.compile(r"\bcreate_task\b"),
    "add_reader": re.compile(r"\badd_reader\b"),
    "add_writer": re.compile(r"\badd_writer\b"),
    "create_server": re.compile(r"\bcreate_server\b"),
    "start_server": re.compile(r"\bstart_server\b"),
    "get_running_loop": re.compile(r"\bget_running_loop\b"),
    "asyncio_sleep": re.compile(r"\basyncio\.sleep\b"),
}

ROOTS = {
    "Lib/asyncio": Path("Lib/asyncio"),
    "Lib/test": Path("Lib/test"),
    "site-packages": Path("/tmp/perf-extra-pkgs"),
}

PACKAGE_HINTS = {
    "uvicorn",
    "fastapi",
    "starlette",
    "httpx",
    "anyio",
    "asgiref",
    "django",
    "celery",
}


def package_name(path: Path, root_name: str) -> str:
    if root_name != "site-packages":
        return root_name
    rel = path.relative_to(ROOTS[root_name])
    return rel.parts[0]


def main() -> None:
    pattern_totals = {name: 0 for name in PATTERNS}
    root_totals = {name: 0 for name in ROOTS}
    package_totals: dict[str, int] = {}
    sample_hits: list[dict[str, object]] = []

    for root_name, root in ROOTS.items():
        for path in root.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = path.read_text(encoding="utf-8", errors="ignore")
            file_hits = {}
            for pattern_name, pattern in PATTERNS.items():
                count = len(pattern.findall(text))
                if count:
                    file_hits[pattern_name] = count
                    pattern_totals[pattern_name] += count
                    root_totals[root_name] += count
            if file_hits:
                pkg = package_name(path, root_name)
                package_totals[pkg] = package_totals.get(pkg, 0) + sum(file_hits.values())
                if root_name != "site-packages" or pkg in PACKAGE_HINTS:
                    sample_hits.append(
                        {
                            "path": str(path),
                            "package": pkg,
                            "hits": file_hits,
                        }
                    )

    top_packages = sorted(
        package_totals.items(),
        key=lambda item: (-item[1], item[0]),
    )[:20]

    result = {
        "roots": root_totals,
        "pattern_totals": pattern_totals,
        "top_packages": top_packages,
        "sample_hits": sample_hits[:200],
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
