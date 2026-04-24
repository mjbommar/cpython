#!/usr/bin/env python3
"""Phase-attribution benchmark for the C compiler pipeline."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import statistics
import subprocess
import sys
import textwrap


LINE_RE = re.compile(
    r"^compile-phase\t"
    r"filename=(?P<filename>[^\t]+)\t"
    r"total_ns=(?P<total>\d+)\t"
    r"new_compiler_ns=(?P<new_compiler>\d+)\t"
    r"setup_ns=(?P<setup>\d+)\t"
    r"preprocess_ns=(?P<preprocess>\d+)\t"
    r"symtable_ns=(?P<symtable>\d+)\t"
    r"compiler_mod_ns=(?P<compiler_mod>\d+)\t"
    r"codegen_ns=(?P<codegen>\d+)\t"
    r"optasm_ns=(?P<optasm>\d+)\t"
    r"code_flags_ns=(?P<code_flags>\d+)\t"
    r"add_return_ns=(?P<add_return>\d+)\t"
    r"code_unit_ns=(?P<code_unit>\d+)\t"
    r"consts_ns=(?P<consts>\d+)\t"
    r"cfg_from_instr_ns=(?P<cfg_from_instr>\d+)\t"
    r"cfg_opt_ns=(?P<cfg_opt>\d+)\t"
    r"cfg_to_instr_ns=(?P<cfg_to_instr>\d+)\t"
    r"assemble_ns=(?P<assemble>\d+)\t"
    r"free_ns=(?P<free>\d+)$"
)


CASES = {
    "A1_module_assign": "x = 1\ny = x + 2\n",
    "A2_module_many_assign": "\n".join(f"x{i} = {i}" for i in range(200)) + "\n",
    "A3_function_module": textwrap.dedent(
        """
        def f(x, y=1):
            z = x + y
            return z
        """
    ),
    "A4_class_module": textwrap.dedent(
        """
        class C:
            x = 1
            def f(self, y):
                return self.x + y
        """
    ),
    "A5_nested_functions": textwrap.dedent(
        """
        def outer(x):
            def inner(y):
                return x + y
            return inner(2)
        """
    ),
    "A6_list_comprehension": "result = [x * 2 for x in range(100)]\n",
}


def _child_code(source: str, label: str, loops: int) -> str:
    return textwrap.dedent(
        f"""
        src = {source!r}
        filename = "[perf-compile]{label}"
        for _ in range({loops}):
            code = compile(src, filename, "exec")
            ns = {{}}
            exec(code, ns, ns)
        """
    )


def _run_case(python: pathlib.Path, label: str, source: str, loops: int) -> dict[str, object]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("PYTHONHASHSEED", "0")
    env["PYTHON_COMPILE_PHASE_STATS"] = "1"
    proc = subprocess.run(
        [str(python), "-S", "-c", _child_code(source, label, loops)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )

    samples = []
    for line in proc.stderr.splitlines():
        match = LINE_RE.match(line)
        if not match:
            continue
        row = {key: int(value) if key != "filename" else value for key, value in match.groupdict().items()}
        if row["filename"] != f"[perf-compile]{label}":
            continue
        samples.append(row)

    if not samples:
        raise RuntimeError(f"no compile-phase samples captured for {label}")

    def mean(field: str) -> float:
        return statistics.fmean(sample[field] for sample in samples)

    total = mean("total")
    return {
        "samples": len(samples),
        "mean_total_ns": round(total, 1),
        "mean_new_compiler_ns": round(mean("new_compiler"), 1),
        "mean_setup_ns": round(mean("setup"), 1),
        "mean_preprocess_ns": round(mean("preprocess"), 1),
        "mean_symtable_ns": round(mean("symtable"), 1),
        "mean_compiler_mod_ns": round(mean("compiler_mod"), 1),
        "mean_codegen_ns": round(mean("codegen"), 1),
        "mean_optasm_ns": round(mean("optasm"), 1),
        "mean_code_flags_ns": round(mean("code_flags"), 1),
        "mean_add_return_ns": round(mean("add_return"), 1),
        "mean_code_unit_ns": round(mean("code_unit"), 1),
        "mean_consts_ns": round(mean("consts"), 1),
        "mean_cfg_from_instr_ns": round(mean("cfg_from_instr"), 1),
        "mean_cfg_opt_ns": round(mean("cfg_opt"), 1),
        "mean_cfg_to_instr_ns": round(mean("cfg_to_instr"), 1),
        "mean_assemble_ns": round(mean("assemble"), 1),
        "mean_free_ns": round(mean("free"), 1),
        "shares_pct": {
            "new_compiler": round(mean("new_compiler") / total * 100, 3),
            "setup": round(mean("setup") / total * 100, 3),
            "preprocess": round(mean("preprocess") / total * 100, 3),
            "symtable": round(mean("symtable") / total * 100, 3),
            "compiler_mod": round(mean("compiler_mod") / total * 100, 3),
            "codegen": round(mean("codegen") / total * 100, 3),
            "optasm": round(mean("optasm") / total * 100, 3),
            "code_flags": round(mean("code_flags") / total * 100, 3),
            "add_return": round(mean("add_return") / total * 100, 3),
            "code_unit": round(mean("code_unit") / total * 100, 3),
            "consts": round(mean("consts") / total * 100, 3),
            "cfg_from_instr": round(mean("cfg_from_instr") / total * 100, 3),
            "cfg_opt": round(mean("cfg_opt") / total * 100, 3),
            "cfg_to_instr": round(mean("cfg_to_instr") / total * 100, 3),
            "assemble": round(mean("assemble") / total * 100, 3),
            "free": round(mean("free") / total * 100, 3),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=pathlib.Path, default=pathlib.Path("./python"))
    parser.add_argument("--loops", type=int, default=120)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    results = {
        "variant": "phase_attribution",
        "python": str(ns.python),
        "loops": ns.loops,
    }
    for label, source in CASES.items():
        results[label] = _run_case(ns.python.resolve(), label, source, ns.loops)

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    for label in CASES:
        data = results[label]
        shares = data["shares_pct"]
        print(
            f"{label}: total={data['mean_total_ns']:.1f} ns "
            f"setup={shares['setup']:.2f}% "
            f"symtable={shares['symtable']:.2f}% "
            f"codegen={shares['codegen']:.2f}% "
            f"optasm={shares['optasm']:.2f}% "
            f"cfg_opt={shares['cfg_opt']:.2f}% "
            f"assemble={shares['assemble']:.2f}%"
        )


if __name__ == "__main__":
    main()
