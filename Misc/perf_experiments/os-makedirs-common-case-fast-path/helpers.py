"""Helpers for the os.makedirs common-case fast-path experiment."""

from __future__ import annotations

import os


ORIGINAL_MAKEDIRS = os.makedirs


def candidate_mkdir_first(name, mode=0o777, exist_ok=False):
    path = os.path
    head, tail = path.split(name)
    if not tail:
        head, tail = path.split(head)

    if head and tail:
        cdir = os.curdir
        if isinstance(tail, bytes):
            cdir = bytes(cdir, "ASCII")
        if tail != cdir:
            try:
                os.mkdir(name, mode)
                return
            except FileNotFoundError:
                pass
            except NotADirectoryError:
                pass
            except OSError:
                if exist_ok and path.isdir(name):
                    return
                raise

    return ORIGINAL_MAKEDIRS(name, mode, exist_ok)


def install_candidate(name: str) -> None:
    if name != "mkdir_first":
        raise ValueError(f"unknown os.makedirs candidate: {name}")
    os.makedirs = candidate_mkdir_first


def restore_original() -> None:
    os.makedirs = ORIGINAL_MAKEDIRS
