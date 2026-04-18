#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gc
import json
import os
import re
import statistics
import sys
import time
from datetime import date, datetime, time as dtime, timezone
from pathlib import Path


SITE_PACKAGES = Path(
    os.environ.get(
        "FROMISOFORMAT_SITE_PACKAGES",
        "/tmp/abc-instancecheck-venv/lib/python3.14/site-packages",
    )
)
if str(SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(SITE_PACKAGES))

JSONSCHEMA_RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$", re.ASCII)


def trimmed_mean(values: list[float]) -> float:
    values = sorted(values)
    if len(values) > 4:
        values = values[1:-1]
    return statistics.mean(values)


def time_callable(fn, repeats: int = 9) -> dict[str, object]:
    samples = []
    gc_state = gc.isenabled()
    gc.disable()
    try:
        for _ in range(repeats):
            start = time.perf_counter()
            fn()
            samples.append(time.perf_counter() - start)
    finally:
        if gc_state:
            gc.enable()
    return {
        "samples_s": samples,
        "trimmed_mean_s": trimmed_mean(samples),
        "min_s": min(samples),
        "max_s": max(samples),
    }


def m1_datetime_seconds_extended() -> None:
    value = "2025-01-02T03:04:05"
    for _ in range(500_000):
        datetime.fromisoformat(value)


def m2_datetime_microseconds_extended() -> None:
    value = "2025-01-02T03:04:05.678901"
    for _ in range(400_000):
        datetime.fromisoformat(value)


def m3_datetime_timezone_extended() -> None:
    value = "2025-01-02T03:04:05.678901+00:00"
    for _ in range(300_000):
        datetime.fromisoformat(value)


def m4_date_extended() -> None:
    value = "2025-01-02"
    for _ in range(800_000):
        date.fromisoformat(value)


def m5_time_extended() -> None:
    value = "03:04:05.678901"
    for _ in range(700_000):
        dtime.fromisoformat(value)


def m6_datetime_week_date() -> None:
    value = "2025-W01-4T12:14:31"
    for _ in range(250_000):
        datetime.fromisoformat(value)


def r1_cattrs_structure_datetime() -> None:
    from cattrs.preconf.json import make_converter

    converter = make_converter()
    value = "2025-01-02T03:04:05.678901+00:00"
    for _ in range(120_000):
        converter.structure(value, datetime)


def r2_sqlalchemy_str_to_datetime() -> None:
    from sqlalchemy.engine._py_processors import str_to_datetime

    value = "2025-01-02 03:04:05.678901"
    for _ in range(250_000):
        str_to_datetime(value)


def r3_sqlalchemy_str_to_date() -> None:
    from sqlalchemy.engine._py_processors import str_to_date

    value = "2025-01-02"
    for _ in range(500_000):
        str_to_date(value)


def r4_sqlalchemy_str_to_time() -> None:
    from sqlalchemy.engine._py_processors import str_to_time

    value = "03:04:05.678901"
    for _ in range(350_000):
        str_to_time(value)


def r5_dataclasses_json_isofield() -> None:
    from dataclasses_json.mm import _IsoField

    field = _IsoField(required=True)
    value = "2025-01-02T03:04:05.678901+00:00"
    for _ in range(160_000):
        field._deserialize(value, "created_at", {})


def r6_jsonschema_is_date() -> None:
    value = "2025-01-02"
    for _ in range(500_000):
        bool(JSONSCHEMA_RE_DATE.fullmatch(value) and date.fromisoformat(value))


def r7_qcore_iso_8601_as_utime() -> None:
    from qcore.microtime import iso_8601_as_utime

    value = "2025-01-02T03:04:05.678901+00:00"
    for _ in range(180_000):
        iso_8601_as_utime(value)


WORKLOADS = {
    "M1_datetime_seconds_extended": m1_datetime_seconds_extended,
    "M2_datetime_microseconds_extended": m2_datetime_microseconds_extended,
    "M3_datetime_timezone_extended": m3_datetime_timezone_extended,
    "M4_date_extended": m4_date_extended,
    "M5_time_extended": m5_time_extended,
    "M6_datetime_week_date": m6_datetime_week_date,
    "R1_cattrs_structure_datetime": r1_cattrs_structure_datetime,
    "R2_sqlalchemy_str_to_datetime": r2_sqlalchemy_str_to_datetime,
    "R3_sqlalchemy_str_to_date": r3_sqlalchemy_str_to_date,
    "R4_sqlalchemy_str_to_time": r4_sqlalchemy_str_to_time,
    "R5_dataclasses_json_isofield": r5_dataclasses_json_isofield,
    "R6_jsonschema_is_date": r6_jsonschema_is_date,
    "R7_qcore_iso_8601_as_utime": r7_qcore_iso_8601_as_utime,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="unspecified")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    results = {
        "label": args.label,
        "python": f"executable={sys.executable}\nversion={sys.version}\nsite_packages={SITE_PACKAGES}",
        "workloads": {},
    }
    for name, fn in WORKLOADS.items():
        results["workloads"][name] = time_callable(fn)

    payload = json.dumps(results, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
