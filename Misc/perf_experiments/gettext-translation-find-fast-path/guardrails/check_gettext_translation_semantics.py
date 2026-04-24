#!/usr/bin/env python3
"""Guardrails for gettext translation/find fast-path experiments."""

from __future__ import annotations

import argparse
import gettext
import os
import pathlib
import tempfile


def main() -> None:
    tmpdir = tempfile.TemporaryDirectory(prefix="gettext-guardrail-")
    localedir = pathlib.Path(tmpdir.name, "locale")
    localedir.mkdir()

    original_language = os.environ.get("LANGUAGE")
    original_lc_all = os.environ.get("LC_ALL")
    original_lc_messages = os.environ.get("LC_MESSAGES")
    original_lang = os.environ.get("LANG")
    current_domain = gettext.textdomain()
    bound_dir = gettext.bindtextdomain(current_domain)

    try:
        os.environ["LANGUAGE"] = "fr_FR.UTF-8@euro:en_US.UTF-8"
        os.environ.pop("LC_ALL", None)
        os.environ.pop("LC_MESSAGES", None)
        os.environ["LANG"] = "C.UTF-8"
        gettext.bindtextdomain(current_domain, str(localedir))

        first = gettext._expand_lang("fr_FR.UTF-8@euro")
        second = gettext._expand_lang("fr_FR.UTF-8@euro")
        assert first == second
        mutated = first
        mutated.append("sentinel")
        third = gettext._expand_lang("fr_FR.UTF-8@euro")
        assert "sentinel" not in third

        assert gettext.find(current_domain, str(localedir), ["fr_FR.UTF-8@euro"], all=True) == []
        assert gettext.find(current_domain, str(localedir), None, all=True) == []
        assert gettext.dgettext(current_domain, "usage:") == "usage:"
        assert gettext.gettext("usage:") == "usage:"

        parser = argparse.ArgumentParser(prog="tool", description="demo")
        parser.add_argument("--count", type=int, required=True)
        parser.add_argument("name", nargs="?")
        help_text = parser.format_help()
        assert "usage:" in help_text
        try:
            parser.parse_args([])
        except SystemExit:
            pass
        else:
            raise AssertionError("expected argparse parse failure")
    finally:
        gettext.bindtextdomain(current_domain, bound_dir)
        if original_language is None:
            os.environ.pop("LANGUAGE", None)
        else:
            os.environ["LANGUAGE"] = original_language
        if original_lc_all is None:
            os.environ.pop("LC_ALL", None)
        else:
            os.environ["LC_ALL"] = original_lc_all
        if original_lc_messages is None:
            os.environ.pop("LC_MESSAGES", None)
        else:
            os.environ["LC_MESSAGES"] = original_lc_messages
        if original_lang is None:
            os.environ.pop("LANG", None)
        else:
            os.environ["LANG"] = original_lang

    print("gettext translation guardrails: ok")


if __name__ == "__main__":
    main()
