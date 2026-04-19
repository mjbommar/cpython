from __future__ import annotations

import html
import os
import sys


if os.path.isdir("/tmp/perf-extra-pkgs") and "/tmp/perf-extra-pkgs" not in sys.path:
    sys.path.insert(0, "/tmp/perf-extra-pkgs")

from django.utils.html import escape as django_escape
from gunicorn.util import write_error as gunicorn_write_error
from pygments.formatters.html import HtmlFormatter
from starlette.middleware.errors import ServerErrorMiddleware


def baseline_escape(s, quote=True):
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    if quote:
        s = s.replace('"', "&quot;")
        s = s.replace("'", "&#x27;")
    return s


class S(str):
    pass


def check_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def check_type(actual, expected_type, label):
    if type(actual) is not expected_type:
        raise AssertionError(f"{label}: expected type {expected_type!r}, got {type(actual)!r}")


def main():
    cases = [
        ("safe", "hello world", True),
        ("safe_noq", "hello world", False),
        ("mixed", "<a href=\"x&y\">O'Reilly</a>", True),
        ("mixed_noq", "/tmp/<x>&y", False),
        ("bmp", "café déjà vu", True),
        ("quotes", "\"double\" 'single'", True),
    ]
    for label, text, quote in cases:
        check_equal(html.escape(text, quote), baseline_escape(text, quote), label)

    subclass = S("hello world")
    escaped = html.escape(subclass)
    check_equal(escaped, "hello world", "subclass_text")
    check_type(escaped, str, "subclass_type")

    for bad in (123, None, b"abc"):
        raised_exc = None
        try:
            html.escape(bad)
        except Exception as exc:
            raised_exc = exc
        else:
            raise AssertionError(f"expected exception for {bad!r}")
        try:
            baseline_escape(bad)
        except Exception as baseline_exc:
            check_type(raised_exc, type(baseline_exc), f"exception_type_{bad!r}")

    check_equal(django_escape("<b>&</b>"), "&lt;b&gt;&amp;&lt;/b&gt;", "django_escape")
    formatter = HtmlFormatter(cssclass='main "class"', filename="unsafe<file>.py")
    check_equal(formatter.cssclass, "main &quot;class&quot;", "pygments_cssclass")
    check_equal(formatter.filename, "unsafe&lt;file&gt;.py", "pygments_filename")

    middleware = ServerErrorMiddleware(app=lambda *args, **kwargs: None, debug=True)
    try:
        raise RuntimeError("boom & bad <value>")
    except RuntimeError as exc:
        html_frame = middleware.generate_html(exc)
        plain = middleware.generate_plain_text(exc)
    if "&lt;" not in html_frame or "&amp;" not in html_frame:
        raise AssertionError("starlette html output missing escapes")
    if "boom & bad <value>" not in plain:
        raise AssertionError("starlette plain text output changed unexpectedly")

    class DummySock:
        def __init__(self):
            self.payload = b""

        def gettimeout(self):
            return 0.0

        def setblocking(self, flag):
            return None

        def send(self, data):
            self.payload += data
            return len(data)

        def sendall(self, data):
            self.payload += data

    sock = DummySock()
    gunicorn_write_error(sock, 400, "Bad Request", "bad <request> & body")
    error_html = sock.payload.decode("latin1")
    if "&lt;request&gt;" not in error_html or "&amp;" not in error_html:
        raise AssertionError("gunicorn output missing escapes")


if __name__ == "__main__":
    main()
