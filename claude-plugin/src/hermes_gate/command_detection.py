from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class BoundaryAction(StrEnum):
    COMMIT = "commit"
    PUSH = "push"
    PR_CREATE = "pr-create"
    PR_READY = "pr-ready"


_CONTROL = {";", "&", "|", "\n", "(", ")"}
_WRAPPERS = {"command", "builtin", "env", "sudo", "nohup"}
_NON_EXECUTORS = {"echo", "printf", "rg", "grep", "sed", "awk", "cat", "less", "head", "tail"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
_SHELL_CONTROL_PREFIXES = {"!", "{", "if", "then", "elif", "else", "while", "until", "do"}


@dataclass(frozen=True)
class BoundaryCommand:
    """A boundary action plus the ``git -C`` directories selecting its repo."""

    action: BoundaryAction
    git_c_dirs: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ShellToken:
    value: str
    quoted: bool = False


def detect_boundary_action(command: str) -> BoundaryAction | None:
    """Return a boundary only when git/gh is the executable in a shell segment."""
    detected = detect_boundary_command(command)
    return detected.action if detected else None


def detect_boundary_command(command: str, *, _depth: int = 0) -> BoundaryCommand | None:
    """Parse a real boundary command, including a bounded ``sh -c`` wrapper.

    This deliberately parses only the command string passed to ``-c``.  It
    does not execute or expand it, so quoted prose remains inert while an
    interpreter wrapper cannot hide an otherwise enforceable Git boundary.
    """
    if _depth > 32:
        return None
    tokens = _lex_shell(command)
    if tokens is None:
        return None
    segments: list[list[_ShellToken]] = [[]]
    for token in tokens:
        if not token.quoted and token.value in _CONTROL:
            segments.append([])
        else:
            segments[-1].append(token)
    for segment in segments:
        detected = _segment_command(segment, _depth=_depth)
        if detected:
            return detected
    return None


def _segment_command(tokens: list[_ShellToken], *, _depth: int) -> BoundaryCommand | None:
    if not tokens:
        return None
    index = 0
    while (
        index < len(tokens)
        and not tokens[index].quoted
        and tokens[index].value in _SHELL_CONTROL_PREFIXES
    ):
        index += 1
    while index < len(tokens) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[index].value):
        index += 1
    while index < len(tokens) and tokens[index].value in _WRAPPERS:
        index += 1
        while index < len(tokens) and tokens[index].value.startswith("-"):
            index += 1
        while index < len(tokens) and re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[index].value
        ):
            index += 1
    if index >= len(tokens):
        return None
    executable = tokens[index].value.rsplit("/", 1)[-1]
    if executable in _NON_EXECUTORS:
        return None
    args = tokens[index + 1 :]
    if executable in _SHELLS:
        script = _shell_command_string(args)
        return detect_boundary_command(script, _depth=_depth + 1) if script is not None else None
    if executable == "git":
        verb, c_dirs = _git_verb_and_c_dirs([item.value for item in args])
        if verb == "commit":
            return BoundaryCommand(BoundaryAction.COMMIT, c_dirs)
        if verb == "push":
            return BoundaryCommand(BoundaryAction.PUSH, c_dirs)
    if executable == "gh":
        words = [part.value for part in args if not part.value.startswith("-")]
        if words[:2] == ["pr", "create"]:
            return BoundaryCommand(BoundaryAction.PR_CREATE)
        if words[:2] == ["pr", "ready"]:
            return BoundaryCommand(BoundaryAction.PR_READY)
    return None


def _shell_command_string(args: list[_ShellToken]) -> str | None:
    """Return the literal command string supplied to a POSIX shell ``-c``."""
    index = 0
    while index < len(args):
        item = args[index].value
        if item in {"-c", "--command"} or (
            item.startswith("-") and not item.startswith("--") and "c" in item[1:]
        ):
            return args[index + 1].value if index + 1 < len(args) else None
        if item.startswith("-"):
            index += 1
            continue
        return None
    return None


def _lex_shell(command: str) -> list[_ShellToken] | None:
    """Tokenize enough POSIX shell syntax for boundary detection, retaining quotes."""
    tokens: list[_ShellToken] = []
    buffer: list[str] = []
    quoted = False
    started = False
    quote: str | None = None
    index = 0

    def emit() -> None:
        nonlocal buffer, quoted, started
        if started:
            tokens.append(_ShellToken("".join(buffer), quoted))
        buffer, quoted, started = [], False, False

    while index < len(command):
        char = command[index]
        if quote is not None:
            if char == quote:
                quote = None
            elif char == "\\" and quote == '"' and index + 1 < len(command):
                index += 1
                buffer.append(command[index])
            else:
                buffer.append(char)
            quoted = True
            started = True
        elif char in {"'", '"'}:
            quote = char
            quoted = True
            started = True
        elif char == "\\" and index + 1 < len(command):
            index += 1
            buffer.append(command[index])
            quoted = True
            started = True
        elif char.isspace():
            emit()
            if char == "\n":
                tokens.append(_ShellToken("\n"))
        elif char in ";&|()":
            emit()
            tokens.append(_ShellToken(char))
        else:
            buffer.append(char)
            started = True
        index += 1
    if quote is not None:
        return None
    emit()
    return tokens


def _git_verb_and_c_dirs(args: list[str]) -> tuple[str | None, tuple[str, ...]]:
    options_with_value = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}
    index = 0
    c_dirs: list[str] = []
    while index < len(args):
        item = args[index]
        if item in options_with_value:
            if item == "-C" and index + 1 < len(args):
                c_dirs.append(args[index + 1])
            index += 2
            continue
        if item.startswith("-C") and len(item) > 2:
            c_dirs.append(item[2:])
            index += 1
            continue
        if item.startswith(("--git-dir=", "--work-tree=", "-c")):
            index += 1
            continue
        if item.startswith("-"):
            index += 1
            continue
        return item, tuple(c_dirs)
    return None, tuple(c_dirs)
