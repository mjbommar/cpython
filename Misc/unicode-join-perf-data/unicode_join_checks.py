from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def load_module():
    path = Path(__file__).with_name("unicode_join_bench.py")
    spec = importlib.util.spec_from_file_location("unicode_join_bench", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    mod = load_module()
    mod.micro_ascii_empty_join()
    mod.micro_bmp_empty_join()
    mod.micro_wide_sep_ascii_join()
    mod.real_jinja2_render()
    mod.real_django_template_render()
    mod.real_django_filter_join()
    mod.real_prompt_toolkit_flush()
    mod.real_jsonschema_error_strings()
    print("unicode join checks passed")


if __name__ == "__main__":
    main()
