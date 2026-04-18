from __future__ import annotations

import argparse
from dataclasses import dataclass
import io
import json
from pathlib import Path
import statistics
import time

from jinja2 import DictLoader, Environment, select_autoescape
from jsonschema import Draft202012Validator
from prompt_toolkit.output.plain_text import PlainTextOutput

from django.conf import settings


if not settings.configured:
    settings.configure(
        DEBUG=False,
        SECRET_KEY="unicode-join-secret",
        USE_I18N=False,
        USE_TZ=False,
        INSTALLED_APPS=[],
        TEMPLATES=[
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "APP_DIRS": False,
                "OPTIONS": {"loaders": [("django.template.loaders.locmem.Loader", {})]},
            }
        ],
    )

import django

django.setup()

from django.template import Context, Engine
from django.template.defaultfilters import join as django_join_filter
from django.utils.safestring import SafeString


ASCII_ITEMS = [f"part{i:03d}" for i in range(256)]
BMP_ITEMS = [f"\u0394{i:03d}" for i in range(256)]
MIXED_ITEMS = [f"ascii{i:03d}" if i % 3 else f"\u0394{i:03d}" for i in range(256)]
SMALL_N_ITEMS = ["alpha", "beta", "gamma"]


JINJA_ENV = Environment(
    loader=DictLoader(
        {
            "report.html": """
            <section>
            {% for order in orders %}
              <article>
                <h2>{{ order.owner|upper }}</h2>
                <p>{{ order.total_cents }}</p>
                <ul>
                {% for item in order["items"] %}
                  <li>{{ item.sku }}={{ item.qty * item.unit_price_cents }}</li>
                {% endfor %}
                </ul>
              </article>
            {% endfor %}
            </section>
            """
        }
    ),
    autoescape=select_autoescape(default_for_string=False),
)
JINJA_TEMPLATE = JINJA_ENV.get_template("report.html")


DJANGO_ENGINE = Engine.get_default()
DJANGO_TEMPLATE = DJANGO_ENGINE.from_string(
    """
    <article>
      <h1>{{ customer|upper }}</h1>
      <ul>
      {% for label in labels %}
        <li>{{ label }}</li>
      {% endfor %}
      </ul>
      <footer>{{ footer }}</footer>
    </article>
    """
)


JSONSCHEMA_VALIDATOR = Draft202012Validator(
    {
        "type": ["string", "number", "object"],
        "patternProperties": {
            "^x-": {"type": "string"},
            "^y-": {"type": "integer"},
        },
        "additionalProperties": False,
    }
)
JSONSCHEMA_INSTANCE = {
    "x-name": 12,
    "y-count": "wrong",
    "extra-a": 1,
    "extra-b": 2,
}


class DummyStdout(io.StringIO):
    def fileno(self) -> int:
        raise OSError("no fileno")


def micro_ascii_empty_join() -> None:
    for _ in range(4_000):
        result = "".join(ASCII_ITEMS)
        if len(result) < 100:
            raise RuntimeError("unexpected join result")


def micro_ascii_sep_join() -> None:
    for _ in range(3_000):
        result = ", ".join(ASCII_ITEMS)
        if ", " not in result:
            raise RuntimeError("unexpected separator join result")


def micro_bmp_empty_join() -> None:
    for _ in range(3_000):
        result = "".join(BMP_ITEMS)
        if "\u0394" not in result:
            raise RuntimeError("unexpected BMP join result")


def micro_wide_sep_ascii_join() -> None:
    for _ in range(2_800):
        result = "🙂".join(ASCII_ITEMS)
        if "🙂" not in result:
            raise RuntimeError("unexpected wide separator join result")


def micro_mixed_width_empty_join() -> None:
    for _ in range(3_000):
        result = "".join(MIXED_ITEMS)
        if "ascii" not in result or "\u0394" not in result:
            raise RuntimeError("unexpected mixed join result")


def micro_small_n_join() -> None:
    for _ in range(180_000):
        result = "".join(SMALL_N_ITEMS)
        if result != "alphabetagamma":
            raise RuntimeError("unexpected small-N result")


def real_jinja2_render() -> None:
    for i in range(4_000):
        orders = []
        for j in range(4):
            items = [
                {"sku": "A100", "qty": (i + j) % 4 + 1, "unit_price_cents": 299},
                {"sku": "B200", "qty": 2, "unit_price_cents": 499},
                {"sku": "C300", "qty": 1, "unit_price_cents": 1299},
            ]
            orders.append(
                {
                    "owner": f"user{(i + j) % 13}",
                    "items": items,
                    "total_cents": sum(item["qty"] * item["unit_price_cents"] for item in items),
                }
            )
        rendered = JINJA_TEMPLATE.render(orders=orders)
        if "<section>" not in rendered:
            raise RuntimeError("jinja2 render missing marker")


def real_django_template_render() -> None:
    for i in range(3_000):
        labels = [f"user{i % 17}:TAG{j}" for j in range(6)]
        rendered = DJANGO_TEMPLATE.render(
            Context(
                {
                    "customer": f"user{i % 17}",
                    "labels": labels,
                    "footer": " | ".join(labels[:3]),
                }
            )
        )
        if "<article>" not in rendered:
            raise RuntimeError("django template missing marker")


def real_django_filter_join() -> None:
    values = [SafeString(f"value{i}") for i in range(10)]
    for _ in range(40_000):
        rendered = django_join_filter(values, ", ", autoescape=True)
        if "," not in rendered:
            raise RuntimeError("django filter join failed")


def real_prompt_toolkit_flush() -> None:
    stdout = DummyStdout()
    output = PlainTextOutput(stdout)
    for i in range(20_000):
        for j in range(8):
            output.write(f"seg{i % 17}:{j};")
        output.flush()
    if stdout.tell() == 0:
        raise RuntimeError("prompt_toolkit flush wrote nothing")


def real_jsonschema_error_strings() -> None:
    for _ in range(6_000):
        errors = list(JSONSCHEMA_VALIDATOR.iter_errors(JSONSCHEMA_INSTANCE))
        rendered = [str(error) for error in errors]
        if not rendered or "is not of type" not in rendered[0]:
            raise RuntimeError("jsonschema workload failed")


WORKLOADS = {
    "M1_ascii_empty_join": micro_ascii_empty_join,
    "M2_ascii_sep_join": micro_ascii_sep_join,
    "M3_bmp_empty_join": micro_bmp_empty_join,
    "M4_wide_sep_ascii_join": micro_wide_sep_ascii_join,
    "M5_mixed_width_empty_join": micro_mixed_width_empty_join,
    "M6_small_n_join": micro_small_n_join,
    "R1_jinja2_render": real_jinja2_render,
    "R2_django_template_render": real_django_template_render,
    "R3_django_filter_join": real_django_filter_join,
    "R4_prompt_toolkit_flush": real_prompt_toolkit_flush,
    "R5_jsonschema_error_strings": real_jsonschema_error_strings,
}


def time_one(fn):
    result = fn()
    if isinstance(result, (int, float)):
        return float(result)
    return None


def run_benchmark(fn, samples: int) -> dict[str, object]:
    measured = []
    for _ in range(samples):
        result = time_one(fn)
        if result is None:
            t0 = time.perf_counter()
            fn()
            result = time.perf_counter() - t0
        measured.append(result)
    trimmed = measured
    if len(measured) > 4:
        trimmed = sorted(measured)[1:-1]
    return {
        "samples_s": measured,
        "trimmed_mean_s": statistics.mean(trimmed),
        "min_s": min(measured),
        "max_s": max(measured),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--workloads", help="Comma-separated subset of workload names")
    args = parser.parse_args()

    selected = WORKLOADS
    if args.workloads:
        names = [name.strip() for name in args.workloads.split(",") if name.strip()]
        selected = {name: WORKLOADS[name] for name in names}

    results = {}
    for name, fn in selected.items():
        results[name] = run_benchmark(fn, samples=args.samples)

    payload = {
        "label": args.label,
        "python": (
            f"executable={Path(__import__('sys').executable)}\n"
            f"version={__import__('sys').version}\n"
            f"cwd={Path.cwd()}"
        ),
        "workloads": results,
    }
    output_path = Path(args.output)
    output_path.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
