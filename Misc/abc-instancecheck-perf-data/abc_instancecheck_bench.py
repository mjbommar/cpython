#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gc
import importlib.util
import inspect
import json
import os
import statistics
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class SupportsClose(Protocol):
    def close(self) -> None: ...


@runtime_checkable
class HasX(Protocol):
    x: int


class Closable:
    def close(self) -> None:
        return None


class HasInstanceX:
    def __init__(self) -> None:
        self.x = 1


class NoX:
    pass


class MappingProxy:
    @property
    def __class__(self):
        return dict


class AwaitableBox:
    def __await__(self):
        if False:
            yield None
        return 1


SITE_PACKAGES = Path(
    os.environ.get(
        "ABC_THIRDPARTY_SITEPACKAGES",
        "/tmp/abc-instancecheck-venv/lib/python3.14/site-packages",
    )
)


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


def load_source_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def m1_mapping_positive_cache() -> None:
    obj = {"a": 1}
    for _ in range(800_000):
        isinstance(obj, Mapping)


def m2_mapping_negative_cache() -> None:
    obj = object()
    for _ in range(800_000):
        isinstance(obj, Mapping)


def m3_proxy_fake_class_positive() -> None:
    obj = MappingProxy()
    for _ in range(200_000):
        isinstance(obj, Mapping)


def m4_protocol_class_method_positive() -> None:
    obj = Closable()
    for _ in range(300_000):
        isinstance(obj, SupportsClose)


def m5_protocol_instance_attr_positive() -> None:
    obj = HasInstanceX()
    for _ in range(300_000):
        isinstance(obj, HasX)


def m6_protocol_negative() -> None:
    obj = NoX()
    for _ in range(300_000):
        isinstance(obj, HasX)


def r1_inspect_isawaitable() -> None:
    obj = AwaitableBox()
    for _ in range(500_000):
        inspect.isawaitable(obj)


def r2_httpx_encode_request_data() -> None:
    from httpx._content import encode_request

    data = {"alpha": "1", "beta": "2", "gamma": "3"}
    for _ in range(120_000):
        encode_request(data=data)


def r3_httpx_encode_request_content_iterable() -> None:
    from httpx._content import encode_request

    body = [b"a", b"b", b"c", b"d"]
    for _ in range(120_000):
        encode_request(content=body)


def r4_typeguard_check_type() -> None:
    from typeguard import CollectionCheckStrategy, TypeCheckConfiguration, TypeCheckMemo
    from typeguard._checkers import check_mapping

    value = {str(i): [i, i + 1, i + 2] for i in range(30)}
    memo = TypeCheckMemo(globals(), locals(), config=TypeCheckConfiguration(
        collection_check_strategy=CollectionCheckStrategy.ALL_ITEMS
    ))
    args = (str, list[int])
    for _ in range(6_000):
        check_mapping(value, dict, args, memo)


def r5_jsonschema_equal() -> None:
    jsonschema_utils = load_source_module(
        "bench_jsonschema_utils",
        SITE_PACKAGES / "jsonschema" / "_utils.py",
    )
    equal = jsonschema_utils.equal

    left = {
        "users": [{"id": i, "roles": ["reader", "writer"], "flags": [True, False]} for i in range(40)],
        "meta": {"page": 1, "count": 40},
    }
    right = {
        "users": [{"id": i, "roles": ["reader", "writer"], "flags": [True, False]} for i in range(40)],
        "meta": {"page": 1, "count": 40},
    }
    for _ in range(4_000):
        equal(left, right)


def r6_jsonschema_validator_protocol() -> None:
    jsonschema_protocols = load_source_module(
        "bench_jsonschema_protocols",
        SITE_PACKAGES / "jsonschema" / "protocols.py",
    )
    Validator = jsonschema_protocols.Validator

    attrs = {
        name: ({} if name in {"META_SCHEMA", "VALIDATORS", "TYPE_CHECKER", "FORMAT_CHECKER", "schema"} else (lambda *args, **kwargs: None))
        for name in Validator.__protocol_attrs__
    }
    validator = type("BenchValidator", (), attrs)()
    for _ in range(200_000):
        isinstance(validator, Validator)


WORKLOADS = {
    "M1_mapping_positive_cache": m1_mapping_positive_cache,
    "M2_mapping_negative_cache": m2_mapping_negative_cache,
    "M3_proxy_fake_class_positive": m3_proxy_fake_class_positive,
    "M4_protocol_class_method_positive": m4_protocol_class_method_positive,
    "M5_protocol_instance_attr_positive": m5_protocol_instance_attr_positive,
    "M6_protocol_negative": m6_protocol_negative,
    "R1_inspect_isawaitable": r1_inspect_isawaitable,
    "R2_httpx_encode_request_data": r2_httpx_encode_request_data,
    "R3_httpx_encode_request_content_iterable": r3_httpx_encode_request_content_iterable,
    "R4_typeguard_check_type": r4_typeguard_check_type,
    "R5_jsonschema_equal": r5_jsonschema_equal,
    "R6_jsonschema_validator_protocol": r6_jsonschema_validator_protocol,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--label", default="unspecified")
    args = parser.parse_args()

    results = {
        "label": args.label,
        "python": inspect.cleandoc(
            f"""
            executable={sys.executable}
            version={sys.version}
            site_packages={SITE_PACKAGES}
            """
        ),
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
