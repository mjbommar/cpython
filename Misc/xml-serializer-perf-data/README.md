# XML Serializer Perf Data

This directory holds the focused benchmark harness for the serializer-first
`xml.etree` experiment.

## Scenarios

- `serialize-root`: serialize the source tree used by the `pyperformance`
  XML benchmark
- `serialize-result`: serialize the transformed result tree from the same workload
- `process`: run the full benchmark-style processing pipeline
- `openpyxl-basic`: build and save the official openpyxl write-performance
  shape using the normal workbook mode
- `openpyxl-write-only`: the same shape using openpyxl's optimised write-only mode
- `openpyxl-styles`: style-heavy workbook save
- `openpyxl-comments`: comment-heavy workbook save
- `openpyxl-charts`: chart-heavy workbook save
- `openpyxl-tables`: table-heavy workbook save

## Run

```bash
./python Misc/xml-serializer-perf-data/xml_serializer_bench.py --scenario all
./python Misc/xml-serializer-perf-data/xml_serializer_bench.py --scenario serialize-root --repeat 10 --iterations 200
/tmp/xml-third-party-envs/main/bin/python Misc/xml-serializer-perf-data/xml_third_party_bench.py --scenario all --repeat 5 --warmup 1
/tmp/xml-third-party-envs/branch/bin/python Misc/xml-serializer-perf-data/xml_third_party_bench.py --scenario openpyxl-comments --repeat 10 --warmup 1
```

The script emits JSON with per-scenario timings so results can be copied into
the branch diary or compared across branches.

## Notes

- The third-party harness currently targets `openpyxl` with `lxml` absent so
  it uses stdlib `xml.etree`.
- `et_xmlfile` was inspected but not used as the primary benchmark target
  because version `2.0.0` vendors its own incremental serializer derived from
  ElementTree, so it does not directly measure this CPython change.
