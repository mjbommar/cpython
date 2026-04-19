#!/usr/bin/env python3

import argparse
import json
import statistics
import time
import xml.etree.ElementTree as ET


def build_xml_tree(etree=ET):
    SubElement = etree.SubElement
    root = etree.Element("root")

    for c in range(50):
        child = SubElement(root, f"child-{c}", tag_type="child")
        for i in range(100):
            SubElement(child, "subchild").text = f"LEAF-{c}-{i}"

    deep = SubElement(root, "deepchildren", tag_type="deepchild")
    for _ in range(50):
        deep = SubElement(deep, "deepchild")
    SubElement(deep, "deepleaf", tag_type="leaf").text = "LEAF"

    root.set("nb-elems", str(sum(1 for _ in root.iter())))
    return root


def build_result_tree(root, etree=ET):
    SubElement = etree.SubElement

    dest = etree.Element("root2")
    target = SubElement(dest, "result-1")
    for child in root:
        SubElement(target, child.tag).text = str(len(child))

    target = SubElement(dest, "result-2")
    for child in root.iterfind(".//subchild"):
        SubElement(target, child.tag, attr=child.text).text = "found"

    checks = {}
    for child in root:
        checks.setdefault(child.get("tag_type"), []).extend(list(child.iter()))

    iterators = {name: iter(items) for name, items in checks.items()}
    target = SubElement(dest, "transform-2")
    for child in root:
        tags = iterators[child.get("tag_type")]
        for sub in child.iter():
            if sub is not next(tags):
                raise RuntimeError("tree iteration consistency check failed")
            SubElement(target, sub.tag).text = "worked"
    return dest


def process(root, etree=ET):
    return etree.tostring(build_result_tree(root, etree), encoding="utf8")


def bench_serialize_root(iterations):
    root = build_xml_tree()
    for _ in range(iterations):
        ET.tostring(root, encoding="utf8")


def bench_serialize_result(iterations):
    root = build_xml_tree()
    dest = build_result_tree(root)
    for _ in range(iterations):
        ET.tostring(dest, encoding="utf8")


def bench_process(iterations):
    root = build_xml_tree()
    for _ in range(iterations):
        process(root)


SCENARIOS = {
    "serialize-root": bench_serialize_root,
    "serialize-result": bench_serialize_result,
    "process": bench_process,
}


def run_case(name, func, iterations, repeat):
    samples = []
    for _ in range(repeat):
        start = time.perf_counter_ns()
        func(iterations)
        elapsed = time.perf_counter_ns() - start
        samples.append(elapsed / 1_000_000)

    return {
        "scenario": name,
        "iterations": iterations,
        "repeat": repeat,
        "mean_ms": statistics.fmean(samples),
        "stdev_ms": statistics.stdev(samples) if len(samples) > 1 else 0.0,
        "min_ms": min(samples),
        "max_ms": max(samples),
        "samples_ms": samples,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        choices=["all", *SCENARIOS],
        default="all",
        help="Scenario to run",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="Inner-loop iterations per sample",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=7,
        help="Number of repeated samples",
    )
    args = parser.parse_args()

    if args.scenario == "all":
        names = list(SCENARIOS)
    else:
        names = [args.scenario]

    results = [
        run_case(name, SCENARIOS[name], args.iterations, args.repeat)
        for name in names
    ]
    print(json.dumps({"results": results}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
