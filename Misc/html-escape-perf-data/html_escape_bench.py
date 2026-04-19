from __future__ import annotations

import argparse
import html
import json
import os
import re
import statistics
import time
from contextlib import contextmanager
from pathlib import Path


if os.path.isdir("/tmp/perf-extra-pkgs") and "/tmp/perf-extra-pkgs" not in os.sys.path:
    os.sys.path.insert(0, "/tmp/perf-extra-pkgs")

from django.conf import settings
from django.utils.html import escape as django_escape
from gunicorn.util import write_error as gunicorn_write_error
from pygments.formatters.html import HtmlFormatter
from starlette.middleware.errors import ServerErrorMiddleware


REPL_Q = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#x27;",
}
REPL_NOQ = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
}
TRANS_Q = str.maketrans(REPL_Q)
TRANS_NOQ = str.maketrans(REPL_NOQ)
REGEX_Q = re.compile(r"[&<>\"']")
REGEX_NOQ = re.compile(r"[&<>]")


def baseline_escape(s, quote=True):
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    if quote:
        s = s.replace('"', "&quot;")
        s = s.replace("'", "&#x27;")
    return s


def _return_base_str(s):
    return s if type(s) is str else s[:]


def c1_noop_then_baseline(s, quote=True):
    if quote:
        if type(s) is str and "&" not in s and "<" not in s and ">" not in s and '"' not in s and "'" not in s:
            return s
    else:
        if type(s) is str and "&" not in s and "<" not in s and ">" not in s:
            return s
    return baseline_escape(s, quote)


def c2_split_quote_paths(s, quote=True):
    amp = "&" in s
    lt = "<" in s
    gt = ">" in s
    if quote:
        dquote = '"' in s
        squote = "'" in s
        if type(s) is str and not (amp or lt or gt or dquote or squote):
            return s
        if amp:
            s = s.replace("&", "&amp;")
        if lt:
            s = s.replace("<", "&lt;")
        if gt:
            s = s.replace(">", "&gt;")
        if dquote:
            s = s.replace('"', "&quot;")
        if squote:
            s = s.replace("'", "&#x27;")
        return _return_base_str(s)
    if type(s) is str and not (amp or lt or gt):
        return s
    if amp:
        s = s.replace("&", "&amp;")
    if lt:
        s = s.replace("<", "&lt;")
    if gt:
        s = s.replace(">", "&gt;")
    return _return_base_str(s)


def c3_find_conditional(s, quote=True):
    amp = s.find("&")
    lt = s.find("<")
    gt = s.find(">")
    if quote:
        dquote = s.find('"')
        squote = s.find("'")
        if type(s) is str and amp < 0 and lt < 0 and gt < 0 and dquote < 0 and squote < 0:
            return s
    else:
        if type(s) is str and amp < 0 and lt < 0 and gt < 0:
            return s
    if amp >= 0:
        s = s.replace("&", "&amp;")
    if lt >= 0:
        s = s.replace("<", "&lt;")
    if gt >= 0:
        s = s.replace(">", "&gt;")
    if quote:
        if dquote >= 0:
            s = s.replace('"', "&quot;")
        if squote >= 0:
            s = s.replace("'", "&#x27;")
    return _return_base_str(s)


def c4_any_scan(s, quote=True):
    specials = ("&", "<", ">", '"', "'") if quote else ("&", "<", ">")
    if type(s) is str and not any(ch in s for ch in specials):
        return s
    return baseline_escape(s, quote)


def c5_translate(s, quote=True):
    regex = REGEX_Q if quote else REGEX_NOQ
    if type(s) is str and regex.search(s) is None:
        return s
    return s.translate(TRANS_Q if quote else TRANS_NOQ)


def c6_regex(s, quote=True):
    regex = REGEX_Q if quote else REGEX_NOQ
    repl = REPL_Q if quote else REPL_NOQ
    if type(s) is str and regex.search(s) is None:
        return s
    return regex.sub(lambda m: repl[m.group(0)], s)


def c7_single_pass(s, quote=True):
    repl = REPL_Q if quote else REPL_NOQ
    start = 0
    parts = None
    for i, ch in enumerate(s):
        rep = repl.get(ch)
        if rep is None:
            continue
        if parts is None:
            parts = []
        if start != i:
            parts.append(s[start:i])
        parts.append(rep)
        start = i + 1
    if parts is None:
        return _return_base_str(s)
    if start != len(s):
        parts.append(s[start:])
    return "".join(parts)


VARIANTS = {
    "baseline": baseline_escape,
    "c1_noop_then_baseline": c1_noop_then_baseline,
    "c2_split_quote_paths": c2_split_quote_paths,
    "c3_find_conditional": c3_find_conditional,
    "c4_any_scan": c4_any_scan,
    "c5_translate": c5_translate,
    "c6_regex": c6_regex,
    "c7_single_pass": c7_single_pass,
    "stdlib": html.escape,
}


@contextmanager
def patched_escape(fn):
    orig_html = html.escape
    orig_django = django_escape
    try:
        html.escape = fn
        import django.utils.html as django_html
        django_html.html.escape = fn
        yield
    finally:
        html.escape = orig_html
        import django.utils.html as django_html
        django_html.html.escape = orig_html


SAFE_SHORT = "hello world"
SAFE_MEDIUM = "The quick brown fox jumps over 13 lazy dogs. " * 6
AMP_ONLY = "A&B&C&D&E&F&G" * 8
ANGLES = "<tag>value</tag>" * 8
QUOTE_HEAVY = "\"single' double\\\" both\"'" * 8
MIXED_HTML = "<a href=\"x&y\">O'Reilly & friends</a>" * 6
TRACEBACKISH = "/tmp/x.py:42 in func <locals> & details \"boom\"" * 4
HTTP_PATH = "/a/b/c?x=<tag>&y=2" * 8
BMP_SAFE = "café déjà vu — пример текста" * 8


def micro_safe_short():
    for _ in range(120_000):
        html.escape(SAFE_SHORT)


def micro_safe_medium():
    for _ in range(24_000):
        html.escape(SAFE_MEDIUM)


def micro_amp_only():
    for _ in range(20_000):
        html.escape(AMP_ONLY)


def micro_angles():
    for _ in range(18_000):
        html.escape(ANGLES)


def micro_quote_heavy():
    for _ in range(16_000):
        html.escape(QUOTE_HEAVY)


def micro_mixed_html():
    for _ in range(16_000):
        html.escape(MIXED_HTML)


def micro_http_path_quote_false():
    for _ in range(20_000):
        html.escape(HTTP_PATH, quote=False)


def micro_bmp_safe():
    for _ in range(24_000):
        html.escape(BMP_SAFE)


def stdlib_http_server():
    samples = [
        "/public/index.html",
        "/reports/<overview>?q=1&lang=en",
        "/weird/space and ünicode/",
        "unsafe\"name'.txt",
    ]
    for _ in range(40_000):
        for item in samples:
            html.escape(item, quote=False)


def stdlib_pydoc_lines():
    lines = [
        'name="value"&extra',
        "<module path>",
        "plain text",
        "quotes ' \" and ampersands &",
    ]
    for _ in range(20_000):
        "<br>".join(html.escape(line) for line in lines)


def django_escape_workload():
    items = [
        "<span>unsafe & text</span>",
        "already-safe text",
        "\"double\" and 'single'",
        "café <déjà>",
    ]
    for _ in range(25_000):
        for item in items:
            django_escape(item)


DJANGO_TABLE_TEMPLATE = None
DJANGO_TABLE_CONTEXT = None


def get_django_template_state():
    global DJANGO_TABLE_TEMPLATE, DJANGO_TABLE_CONTEXT
    if DJANGO_TABLE_TEMPLATE is None:
        if not settings.configured:
            settings.configure(
                TEMPLATES=[{"BACKEND": "django.template.backends.django.DjangoTemplates"}]
            )
        import django

        django.setup()
        from django.template import Context, Template

        DJANGO_TABLE_TEMPLATE = Template(
            """<table>
{% for row in table %}
<tr>{% for col in row %}<td>{{ col|escape }}</td>{% endfor %}</tr>
{% endfor %}
</table>"""
        )
        DJANGO_TABLE_CONTEXT = Context({"table": [range(80) for _ in range(80)]})
    return DJANGO_TABLE_TEMPLATE, DJANGO_TABLE_CONTEXT


def django_template_workload():
    template, context = get_django_template_state()
    for _ in range(12):
        rendered = template.render(context)
        if "<table>" not in rendered:
            raise RuntimeError("django template render failed")


def starlette_error_workload():
    middleware = ServerErrorMiddleware(app=lambda *args, **kwargs: None, debug=True)
    for _ in range(7_500):
        try:
            raise RuntimeError("boom & bad <value>")
        except RuntimeError as exc:
            middleware.generate_html(exc)
            middleware.generate_plain_text(exc)


def gunicorn_error_workload():
    class DummySock:
        def gettimeout(self):
            return 0.0

        def setblocking(self, flag):
            return None

        def send(self, data):
            return len(data)

        def sendall(self, data):
            return None

    sock = DummySock()
    for _ in range(10_000):
        gunicorn_write_error(sock, 400, "Bad Request", "bad <request> & body")


def pygments_options_workload():
    options = {
        "cssclass": 'main "class"',
        "cssstyles": "color:red&blue",
        "filename": "unsafe<file>.py",
        "lineseparator": "\n",
        "lineanchors": "anchor&x",
        "linespans": "span<y>",
    }
    for _ in range(7_500):
        HtmlFormatter(**options)


WORKLOADS = {
    "M1_safe_short": micro_safe_short,
    "M2_safe_medium": micro_safe_medium,
    "M3_amp_only": micro_amp_only,
    "M4_angles": micro_angles,
    "M5_quote_heavy": micro_quote_heavy,
    "M6_mixed_html": micro_mixed_html,
    "M7_http_path_quote_false": micro_http_path_quote_false,
    "M8_bmp_safe": micro_bmp_safe,
    "R1_stdlib_http_server": stdlib_http_server,
    "R2_stdlib_pydoc_lines": stdlib_pydoc_lines,
    "R3_django_escape": django_escape_workload,
    "R4_django_template": django_template_workload,
    "R5_starlette_error": starlette_error_workload,
    "R6_gunicorn_error": gunicorn_error_workload,
    "R7_pygments_options": pygments_options_workload,
}


def time_one(fn):
    start = time.perf_counter()
    fn()
    return time.perf_counter() - start


def run_bench(label: str, variant: str, samples: int):
    bench_fn = VARIANTS[variant]
    results = {}
    with patched_escape(bench_fn):
        for name, workload in WORKLOADS.items():
            values = [time_one(workload) for _ in range(samples)]
            results[name] = {
                "min": min(values),
                "median": statistics.median(values),
                "samples": values,
            }
    return {
        "label": label,
        "variant": variant,
        "python": os.sys.version,
        "workloads": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--variant", default="baseline", choices=sorted(VARIANTS))
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = run_bench(args.label, args.variant, args.samples)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
