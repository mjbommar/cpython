import argparse


ORIGINAL_PARSE_KNOWN_ARGS = argparse.ArgumentParser._parse_known_args


def fast_parse_known_args_no_mutex(self, arg_strings, namespace, intermixed):
    option_string_indices = {}
    arg_string_pattern_parts = []
    arg_strings_iter = iter(arg_strings)
    for i, arg_string in enumerate(arg_strings_iter):
        if arg_string == "--":
            arg_string_pattern_parts.append("-")
            for arg_string in arg_strings_iter:
                arg_string_pattern_parts.append("A")
        else:
            option_tuples = self._parse_optional(arg_string)
            if option_tuples is None:
                pattern = "A"
            else:
                option_string_indices[i] = option_tuples
                pattern = "O"
            arg_string_pattern_parts.append(pattern)

    arg_strings_pattern = "".join(arg_string_pattern_parts)

    seen_actions = set()
    warned = set()

    def take_action(action, argument_strings, option_string=None):
        seen_actions.add(action)
        argument_values = self._get_values(action, argument_strings)
        if argument_values is not argparse.SUPPRESS:
            action(self, namespace, argument_values, option_string)

    def consume_optional(start_index):
        option_tuples = option_string_indices[start_index]
        if len(option_tuples) > 1:
            options = ", ".join(
                [option_string for action, option_string, sep, explicit_arg in option_tuples]
            )
            args = {"option": arg_strings[start_index], "matches": options}
            msg = argparse._("ambiguous option: %(option)s could match %(matches)s")
            raise argparse.ArgumentError(None, msg % args)

        action, option_string, sep, explicit_arg = option_tuples[0]
        match_argument = self._match_argument
        action_tuples = []
        while True:
            if action is None:
                extras.append(arg_strings[start_index])
                extras_pattern.append("O")
                return start_index + 1

            if explicit_arg is not None:
                arg_count = match_argument(action, "A")
                chars = self.prefix_chars
                if (
                    arg_count == 0
                    and option_string[1] not in chars
                    and explicit_arg != ""
                ):
                    if sep or explicit_arg[0] in chars:
                        msg = argparse._("ignored explicit argument %r")
                        raise argparse.ArgumentError(action, msg % explicit_arg)
                    action_tuples.append((action, [], option_string))
                    char = option_string[0]
                    option_string = char + explicit_arg[0]
                    optionals_map = self._option_string_actions
                    if option_string in optionals_map:
                        action = optionals_map[option_string]
                        explicit_arg = explicit_arg[1:]
                        if not explicit_arg:
                            sep = explicit_arg = None
                        elif explicit_arg[0] == "=":
                            sep = "="
                            explicit_arg = explicit_arg[1:]
                        else:
                            sep = ""
                    else:
                        extras.append(char + explicit_arg)
                        extras_pattern.append("O")
                        stop = start_index + 1
                        break
                elif arg_count == 1:
                    stop = start_index + 1
                    args = [explicit_arg]
                    action_tuples.append((action, args, option_string))
                    break
                else:
                    msg = argparse._("ignored explicit argument %r")
                    raise argparse.ArgumentError(action, msg % explicit_arg)
            else:
                start = start_index + 1
                selected_patterns = arg_strings_pattern[start:]
                arg_count = match_argument(action, selected_patterns)
                stop = start + arg_count
                args = arg_strings[start:stop]
                action_tuples.append((action, args, option_string))
                break

        assert action_tuples
        for action, args, option_string in action_tuples:
            if action.deprecated and option_string not in warned:
                self._warning(
                    argparse._("option '%(option)s' is deprecated")
                    % {"option": option_string}
                )
                warned.add(option_string)
            take_action(action, args, option_string)
        return stop

    positionals = self._get_positional_actions()

    def consume_positionals(start_index):
        match_partial = self._match_arguments_partial
        selected_pattern = arg_strings_pattern[start_index:]
        arg_counts = match_partial(positionals, selected_pattern)

        for action, arg_count in zip(positionals, arg_counts):
            args = arg_strings[start_index : start_index + arg_count]
            if action.nargs == argparse.PARSER:
                if arg_strings_pattern[start_index] == "-":
                    assert args[0] == "--"
                    args.remove("--")
            elif action.nargs != argparse.REMAINDER:
                if arg_strings_pattern.find("-", start_index, start_index + arg_count) >= 0:
                    args.remove("--")
            start_index += arg_count
            if args and action.deprecated and action.dest not in warned:
                self._warning(
                    argparse._("argument '%(argument_name)s' is deprecated")
                    % {"argument_name": action.dest}
                )
                warned.add(action.dest)
            take_action(action, args)

        positionals[:] = positionals[len(arg_counts) :]
        return start_index

    extras = []
    extras_pattern = []
    start_index = 0
    if option_string_indices:
        max_option_string_index = max(option_string_indices)
    else:
        max_option_string_index = -1
    while start_index <= max_option_string_index:
        next_option_string_index = start_index
        while next_option_string_index <= max_option_string_index:
            if next_option_string_index in option_string_indices:
                break
            next_option_string_index += 1
        if not intermixed and start_index != next_option_string_index:
            positionals_end_index = consume_positionals(start_index)
            if positionals_end_index > start_index:
                start_index = positionals_end_index
                continue
            else:
                start_index = positionals_end_index

        if start_index not in option_string_indices:
            strings = arg_strings[start_index:next_option_string_index]
            extras.extend(strings)
            extras_pattern.extend(arg_strings_pattern[start_index:next_option_string_index])
            start_index = next_option_string_index

        start_index = consume_optional(start_index)

    if not intermixed:
        stop_index = consume_positionals(start_index)
        extras.extend(arg_strings[stop_index:])
    else:
        extras.extend(arg_strings[start_index:])
        extras_pattern.extend(arg_strings_pattern[start_index:])
        extras_pattern = "".join(extras_pattern)
        assert len(extras_pattern) == len(extras)
        arg_strings = [s for s, c in zip(extras, extras_pattern) if c != "O"]
        arg_strings_pattern = extras_pattern.replace("O", "")
        stop_index = consume_positionals(0)
        for i, c in enumerate(extras_pattern):
            if not stop_index:
                break
            if c != "O":
                stop_index -= 1
                extras[i] = None
        extras = [s for s in extras if s is not None]

    required_actions = []
    for action in self._actions:
        if action not in seen_actions:
            if action.required:
                required_actions.append(argparse._get_action_name(action))
            else:
                if (
                    action.default is not None
                    and isinstance(action.default, str)
                    and hasattr(namespace, action.dest)
                    and action.default is getattr(namespace, action.dest)
                ):
                    setattr(namespace, action.dest, self._get_value(action, action.default))

    if required_actions:
        raise argparse.ArgumentError(
            None,
            argparse._("the following arguments are required: %s")
            % ", ".join(required_actions),
        )

    return namespace, extras


def candidate_parse_known_args(self, arg_strings, namespace, intermixed):
    if self.fromfile_prefix_chars is None and not self._mutually_exclusive_groups:
        return fast_parse_known_args_no_mutex(self, arg_strings, namespace, intermixed)
    return ORIGINAL_PARSE_KNOWN_ARGS(self, arg_strings, namespace, intermixed)


def install_candidate():
    argparse.ArgumentParser._parse_known_args = candidate_parse_known_args


def restore_original():
    argparse.ArgumentParser._parse_known_args = ORIGINAL_PARSE_KNOWN_ARGS
