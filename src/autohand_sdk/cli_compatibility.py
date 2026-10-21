"""Reject legacy generated switches that are absent from the current CLI."""

from __future__ import annotations

_UNSUPPORTED = frozenset(
    [
        "--agents-md",
        "--no-agents-md",
        "--agents-md-create",
        "--agents-md-auto-update",
        "--agents-md-path",
        "--auto-save-interval",
        "--compression-threshold",
        "--summarization-threshold",
        "--skills",
        "--skill-sources",
        "--install-missing-skills",
        "--permission-mode",
        "--permission-allow-list",
        "--permission-deny-list",
    ]
)
_SWITCHES = frozenset(
    [
        "--bare",
        "--offline",
        "--yes",
        "--y",
        "--dry-run",
        "--debug",
        "--auto-commit",
        "-c",
        "--unrestricted",
        "--restricted",
        "--plan",
        "--answer-only",
        "--setup-only",
        "--no-idle-logout",
        "--auto-skill",
        "--learn",
        "--learn-update",
        "--project",
        "--permissions",
        "--settings",
        "--traces-on",
        "--traces-off",
        "--login",
        "--logout",
        "--patch",
        "--acp",
        "--sdk-resume-last",
        "--tmux",
        "--auto-mode",
        "--no-worktree",
        "--interactive-on-complete",
        "--setup",
        "--about",
        "--feedback",
        "--cc",
        "--context-compact",
        "--no-cc",
        "--no-context-compact",
        "--ephemeral",
    ]
)


def validate_cli_arguments(arguments: list[str]) -> None:
    """Check option tokens while preserving arbitrary prompt and other argument values."""
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument in _UNSUPPORTED:
            raise ValueError(
                argument
                + " is unsupported by the current CLI; use a supported CLI option or runtime RPC instead"
            )
        index += 1 if argument in _SWITCHES else 2
