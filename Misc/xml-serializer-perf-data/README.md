# XML Serializer Perf Data

This directory holds the focused benchmark harness for the serializer-first
`xml.etree` experiment.

## Scenarios

- `serialize-root`: serialize the source tree used by the `pyperformance`
  XML benchmark
- `serialize-result`: serialize the transformed result tree from the same workload
- `process`: run the full benchmark-style processing pipeline

## Run

```bash
./python Misc/xml-serializer-perf-data/xml_serializer_bench.py --scenario all
./python Misc/xml-serializer-perf-data/xml_serializer_bench.py --scenario serialize-root --repeat 10 --iterations 200
```

The script emits JSON with per-scenario timings so results can be copied into
the branch diary or compared across branches.
