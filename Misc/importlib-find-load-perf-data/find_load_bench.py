import importlib
import importlib._bootstrap as bootstrap
import os
import pathlib
import pyperf
import sys
import tempfile


ROOT = pathlib.Path(tempfile.mkdtemp(prefix="importlib_find_load_"))
PKG = ROOT / "_ifl_pkg"
PKG.mkdir()
(PKG / "__init__.py").write_text("value = 1\n", encoding="utf-8")

for i in range(16):
    (ROOT / f"_ifl_mod_{i}.py").write_text(f"value = {i}\n", encoding="utf-8")
    (PKG / f"child_{i}.py").write_text(f"value = {i}\n", encoding="utf-8")

sys.path.insert(0, os.fspath(ROOT))
importlib.invalidate_caches()
importlib.import_module("_ifl_pkg")


def _clear_module(name):
    sys.modules.pop(name, None)


def bench_loaded_builtin(loops):
    find_and_load = bootstrap._find_and_load
    import_ = bootstrap._gcd_import
    name = "sys"
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        find_and_load(name, import_)
    return pyperf.perf_counter() - t0


def bench_loaded_python(loops):
    find_and_load = bootstrap._find_and_load
    import_ = bootstrap._gcd_import
    name = "importlib"
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        find_and_load(name, import_)
    return pyperf.perf_counter() - t0


def bench_reload_top_level(loops):
    import_module = importlib.import_module
    names = [f"_ifl_mod_{i}" for i in range(16)]
    t0 = pyperf.perf_counter()
    for i in range(loops):
        name = names[i & 15]
        _clear_module(name)
        import_module(name)
    return pyperf.perf_counter() - t0


def bench_reload_package_child(loops):
    import_module = importlib.import_module
    pkg = sys.modules["_ifl_pkg"]
    names = [f"_ifl_pkg.child_{i}" for i in range(16)]
    attrs = [f"child_{i}" for i in range(16)]
    t0 = pyperf.perf_counter()
    for i in range(loops):
        j = i & 15
        name = names[j]
        _clear_module(name)
        try:
            delattr(pkg, attrs[j])
        except AttributeError:
            pass
        import_module(name)
    return pyperf.perf_counter() - t0


def bench_missing_top_level(loops):
    import_module = importlib.import_module
    name = "_ifl_missing_module"
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        try:
            import_module(name)
        except ModuleNotFoundError:
            pass
    return pyperf.perf_counter() - t0


def bench_missing_package_child(loops):
    import_module = importlib.import_module
    name = "_ifl_pkg.missing_child"
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        try:
            import_module(name)
        except ModuleNotFoundError:
            pass
    return pyperf.perf_counter() - t0


def main():
    runner = pyperf.Runner()
    runner.bench_time_func("loaded_builtin", bench_loaded_builtin)
    runner.bench_time_func("loaded_python", bench_loaded_python)
    runner.bench_time_func("reload_top_level", bench_reload_top_level)
    runner.bench_time_func("reload_package_child", bench_reload_package_child)
    runner.bench_time_func("missing_top_level", bench_missing_top_level)
    runner.bench_time_func("missing_package_child", bench_missing_package_child)


if __name__ == "__main__":
    main()
