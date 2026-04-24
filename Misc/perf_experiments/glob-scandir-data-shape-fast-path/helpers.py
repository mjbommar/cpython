from __future__ import annotations

import glob
import os


ORIGINAL_WILDCARD_SELECTOR = glob._StringGlobber.wildcard_selector
ORIGINAL_RECURSIVE_SELECTOR = glob._StringGlobber.recursive_selector


def _string_scandir(path):
    # Mirror the production requirement to close scandir() before iterating.
    with os.scandir(path) as scandir_it:
        return list(scandir_it)


def _prepare_recursive_selector(self, part, parts):
    while parts and parts[-1] == "**":
        parts.pop()

    follow_symlinks = self.recursive is not glob._no_recurse_symlinks
    if follow_symlinks:
        while parts and parts[-1] not in glob._special_parts:
            part += self.sep + parts.pop()

    match = None if part == "**" else self.compile(part)
    dir_only = bool(parts)
    select_next = self.selector(parts)
    return follow_symlinks, match, dir_only, select_next


def candidate_recursive_selector(self, part, parts):
    follow_symlinks, match, dir_only, select_next = _prepare_recursive_selector(
        self, part, parts
    )

    def select_recursive(path, exists=False):
        path_str = self.stringify_path(path)
        match_pos = len(path_str)
        if match is None or match(path_str, match_pos):
            yield from select_next(path, exists)
        stack = [path]
        while stack:
            path = stack.pop()
            try:
                entries = _string_scandir(path)
            except OSError:
                continue
            for entry in entries:
                is_dir = False
                try:
                    if entry.is_dir(follow_symlinks=follow_symlinks):
                        is_dir = True
                except OSError:
                    pass

                if not is_dir and dir_only:
                    continue

                entry_path = entry.path
                if dir_only:
                    entry_path_dir = self.concat_path(entry_path, self.sep)
                if match is None or match(entry_path, match_pos):
                    if dir_only:
                        yield from select_next(entry_path_dir, exists=True)
                    else:
                        yield entry_path
                if is_dir:
                    stack.append(entry_path)

    return select_recursive


def candidate_wildcard_selector(self, part, parts):
    match = None if part == "*" else self.compile(part)
    dir_only = bool(parts)
    if dir_only:
        select_next = self.selector(parts)

    def select_wildcard(path, exists=False):
        try:
            entries = _string_scandir(path)
        except OSError:
            return

        if match is None:
            for entry in entries:
                if dir_only:
                    try:
                        if not entry.is_dir():
                            continue
                    except OSError:
                        continue
                    yield from select_next(
                        self.concat_path(entry.path, self.sep), exists=True
                    )
                else:
                    yield entry.path
            return

        for entry in entries:
            if not match(entry.name):
                continue
            if dir_only:
                try:
                    if not entry.is_dir():
                        continue
                except OSError:
                    continue
                yield from select_next(
                    self.concat_path(entry.path, self.sep), exists=True
                )
            else:
                yield entry.path

    return select_wildcard


def install_candidate(variant="recursive_only"):
    if variant == "recursive_only":
        glob._StringGlobber.recursive_selector = candidate_recursive_selector
        glob._StringGlobber.wildcard_selector = ORIGINAL_WILDCARD_SELECTOR
        return
    if variant == "both_selectors":
        glob._StringGlobber.recursive_selector = candidate_recursive_selector
        glob._StringGlobber.wildcard_selector = candidate_wildcard_selector
        return
    raise ValueError(f"unknown variant: {variant}")


def restore_original():
    glob._StringGlobber.recursive_selector = ORIGINAL_RECURSIVE_SELECTOR
    glob._StringGlobber.wildcard_selector = ORIGINAL_WILDCARD_SELECTOR
