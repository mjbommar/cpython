"""Aggregate per-run bench JSONs into per-config medians and deltas."""
import glob
import json
import statistics
import sys
from pathlib import Path


BENCH_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/json-bench")
BASELINE = sys.argv[2] if len(sys.argv) > 2 else "main"
# Configs inferred from filenames; file format: <config>-run<n>.json
configs = sorted({f.name.split("-run")[0]
                  for f in BENCH_DIR.glob("*-run*.json")})
# Put baseline first
if BASELINE in configs:
    configs.remove(BASELINE)
    configs.insert(0, BASELINE)

def load(cfg):
    files = sorted(BENCH_DIR.glob(f"{cfg}-run*.json"))
    if not files:
        return None
    runs = [json.load(open(f)) for f in files]
    scenarios = list(runs[0].keys())
    agg = {}
    for sc in scenarios:
        pooled = []
        for r in runs:
            pooled.extend(r[sc]["runs"])
        pooled.sort()
        trim = max(1, len(pooled) // 7)
        trimmed = pooled[trim:-trim]
        n = runs[0][sc]["n"]
        agg[sc] = {
            "n": n,
            "median": statistics.median(pooled),
            "trimmed_mean": statistics.mean(trimmed),
            "min": min(pooled),
            "per_call_us": statistics.mean(trimmed) * 1e6 / n,
        }
    return agg

data = {c: load(c) for c in configs}
data = {c: d for c, d in data.items() if d}

if BASELINE not in data:
    print("no baseline data")
    sys.exit(1)

scenarios = list(data[BASELINE].keys())
print(f"\n{'scenario':<28}", end="")
for c in data:
    print(f"{c:>12}", end="")
print()
print("-" * (28 + 12 * len(data)))
for sc in scenarios:
    print(f"{sc:<28}", end="")
    for c in data:
        print(f"{data[c][sc]['per_call_us']:>12.3f}", end="")
    print()

label = f"scenario (% vs {BASELINE})"
print(f"\n{label:<28}", end="")
for c in data:
    print(f"{c:>12}", end="")
print()
for sc in scenarios:
    print(f"{sc:<28}", end="")
    base = data[BASELINE][sc]["per_call_us"]
    for c in data:
        delta = (data[c][sc]["per_call_us"] - base) / base * 100
        print(f"{delta:>+11.1f}%", end="")
    print()
