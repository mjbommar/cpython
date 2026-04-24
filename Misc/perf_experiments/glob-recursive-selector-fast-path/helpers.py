import glob


ORIGINAL_RECURSIVE_SELECTOR = glob._GlobberBase.recursive_selector


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
    """Runtime prototype for lazy stringify_path() in recursive walk."""
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
            yield from select_recursive_step(stack, match_pos)

    def select_recursive_step(stack, match_pos):
        path = stack.pop()
        try:
            entries = self.scandir(path)
        except OSError:
            pass
        else:
            for entry, _entry_name, entry_path in entries:
                is_dir = False
                try:
                    if entry.is_dir(follow_symlinks=follow_symlinks):
                        is_dir = True
                except OSError:
                    pass

                if is_dir or not dir_only:
                    if dir_only:
                        entry_path_dir = self.concat_path(entry_path, self.sep)
                    if match is None:
                        matched = True
                    else:
                        entry_path_str = self.stringify_path(entry_path)
                        matched = bool(match(entry_path_str, match_pos))
                    if matched:
                        if dir_only:
                            yield from select_next(entry_path_dir, exists=True)
                        else:
                            yield entry_path
                    if is_dir:
                        stack.append(entry_path)

    return select_recursive


def candidate_recursive_selector_inline(self, part, parts):
    """Runtime prototype with inlined step loop plus lazy stringify."""
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
                entries = self.scandir(path)
            except OSError:
                continue
            for entry, _entry_name, entry_path in entries:
                is_dir = False
                try:
                    if entry.is_dir(follow_symlinks=follow_symlinks):
                        is_dir = True
                except OSError:
                    pass

                if not is_dir and dir_only:
                    continue
                if dir_only:
                    entry_path_dir = self.concat_path(entry_path, self.sep)
                if match is None:
                    matched = True
                else:
                    entry_path_str = self.stringify_path(entry_path)
                    matched = bool(match(entry_path_str, match_pos))
                if matched:
                    if dir_only:
                        yield from select_next(entry_path_dir, exists=True)
                    else:
                        yield entry_path
                if is_dir:
                    stack.append(entry_path)

    return select_recursive


def install_candidate(variant="lazy_stringify"):
    if variant == "lazy_stringify":
        glob._GlobberBase.recursive_selector = candidate_recursive_selector
    elif variant == "inline_step":
        glob._GlobberBase.recursive_selector = candidate_recursive_selector_inline
    else:
        raise ValueError(f"unknown variant: {variant}")


def restore_original():
    glob._GlobberBase.recursive_selector = ORIGINAL_RECURSIVE_SELECTOR
