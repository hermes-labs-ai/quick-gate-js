"""The hook parser must recognize executable commands, not quoted text."""

from __future__ import annotations

import shlex

import pytest

from hermes_gate.command_detection import (
    BoundaryAction,
    detect_boundary_action,
    detect_boundary_command,
)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git commit -m 'gate receipt'", BoundaryAction.COMMIT),
        ("git -C /tmp/example commit --no-verify -m done", BoundaryAction.COMMIT),
        ("env GIT_EDITOR=true git push origin main", BoundaryAction.PUSH),
        ("git push --set-upstream origin codex/gate", BoundaryAction.PUSH),
        ("gh pr create --title gate --body ready", BoundaryAction.PR_CREATE),
        ("gh pr ready 42", BoundaryAction.PR_READY),
        ("FOO=1 gh pr create --fill", BoundaryAction.PR_CREATE),
        ("sh -c 'git commit -m done'", BoundaryAction.COMMIT),
        ("bash -c 'git push origin main'", BoundaryAction.PUSH),
        ("bash -lc 'git push origin main'", BoundaryAction.PUSH),
        ("zsh -c 'gh pr create --fill'", BoundaryAction.PR_CREATE),
        ("env CI=1 sh -c 'gh pr ready 42'", BoundaryAction.PR_READY),
    ],
)
def test_detects_real_boundary_commands(command: str, expected: BoundaryAction) -> None:
    assert detect_boundary_action(command) is expected


@pytest.mark.parametrize(
    "command",
    [
        "echo 'git commit -m nope'",
        "printf '%s\\n' 'gh pr create --fill'",
        "rg 'git push' README.md",
        "git log --oneline --all",
        "git status --short",
        "gh pr list",
        "python -c \"print('git commit -m nope')\"",
        "# git push origin main",
    ],
)
def test_ignores_quoted_prose_logs_and_non_boundary_git(command: str) -> None:
    assert detect_boundary_action(command) is None


def test_detects_commands_after_a_shell_separator() -> None:
    assert detect_boundary_action("pytest -q && git commit -m done") is BoundaryAction.COMMIT


def test_does_not_treat_a_git_word_after_separator_as_a_command_argument() -> None:
    assert detect_boundary_action("echo done && printf '%s' 'git push origin main'") is None


def test_captures_ordered_git_c_directories_inside_a_shell_wrapper() -> None:
    detected = detect_boundary_command("bash -c 'git -C first -C second commit -m done'")
    assert detected is not None
    assert detected.action is BoundaryAction.COMMIT
    assert detected.git_c_dirs == ("first", "second")


def test_shell_wrapper_does_not_treat_quoted_prose_as_a_boundary() -> None:
    assert detect_boundary_action("sh -c \"echo 'git commit -m nope'\"") is None


def test_detects_boundary_inside_shell_control_flow() -> None:
    assert (
        detect_boundary_action("sh -c 'if true; then git push origin main; fi'")
        is BoundaryAction.PUSH
    )


@pytest.mark.parametrize("word", ["!", "then", "if", "do", "{"])
def test_quoted_shell_control_word_is_not_treated_as_syntax(word: str) -> None:
    command = f'''sh -c '"{word}" git push origin main' '''
    assert detect_boundary_action(command) is None


def test_partially_quoted_shell_control_word_is_not_treated_as_syntax() -> None:
    assert detect_boundary_action("sh -c 'i\"f\" git push origin main'") is None


def test_detects_more_than_five_nested_shell_wrappers() -> None:
    command = "git commit -m nested"
    for _ in range(8):
        command = shlex.join(["sh", "-c", command])
    assert detect_boundary_action(command) is BoundaryAction.COMMIT
