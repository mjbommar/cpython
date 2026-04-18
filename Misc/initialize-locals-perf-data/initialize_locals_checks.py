from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
BENCH = ROOT / "initialize_locals_bench.py"
spec = importlib.util.spec_from_file_location("initialize_locals_bench", BENCH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def main() -> None:
    assert module.micro_exact_positional(10) > 0
    assert module.micro_defaults_fill(10) > 0
    assert module.micro_keyword_call(10) > 0
    assert module.micro_varargs_call(10) > 0
    assert module.micro_bound_method(10) > 0
    assert module.micro_closure_call(10) > 0
    assert module.micro_many9_call(10) > 0
    module.real_jinja2_render(3)
    module.real_django_template(3)
    module.real_jsonschema_validate(3)
    module.real_celery_eager(3)
    print("initialize_locals checks passed")


if __name__ == "__main__":
    main()
