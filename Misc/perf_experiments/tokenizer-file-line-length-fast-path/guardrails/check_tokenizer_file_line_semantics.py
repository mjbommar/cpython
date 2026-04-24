#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=Path, default=Path("./python"))
    return parser.parse_args()


def run(python: Path, script: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("PYTHONHASHSEED", "0")
    return subprocess.run(
        [str(python), "-S", "-B", str(script)],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def main() -> int:
    args = parse_args()
    python = args.python.resolve()
    with tempfile.TemporaryDirectory(prefix="tokenizer-file-guardrail-") as tmp:
        root = Path(tmp)

        utf8_cookie = root / "utf8_cookie.py"
        utf8_cookie.write_text(
            "#!/usr/bin/env python3\n"
            "# coding: utf-8\n"
            + ("# comment\n" * 200)
            + "print('ok')\n",
            encoding="utf-8",
        )
        proc = run(python, utf8_cookie)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout == "ok\n", proc.stdout

        latin1_cookie = root / "latin1_cookie.py"
        latin1_cookie.write_bytes(
            (
                "# coding: latin-1\n"
                + ("# ol\xe1\n" * 200)
                + "print('ol\xe1')\n"
            ).encode("latin-1")
        )
        proc = run(python, latin1_cookie)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout == "ol\xe1\n", proc.stdout

        no_trailing_newline = root / "no_trailing_newline.py"
        no_trailing_newline.write_text("x = 1", encoding="utf-8")
        proc = run(python, no_trailing_newline)
        assert proc.returncode == 0, proc.stderr

        syntax_error = root / "syntax_error.py"
        syntax_error.write_text(
            "# comment\n"
            "# comment\n"
            "if True print('bad')\n",
            encoding="utf-8",
        )
        proc = run(python, syntax_error)
        assert proc.returncode != 0
        assert "line 3" in proc.stderr, proc.stderr

    print("tokenizer file line semantics: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
