from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Iterable

from django.apps import apps
from django.core.management import call_command

logger = logging.getLogger(__name__)

_DISABLE_VALUES: set[str] = {"0", "false", "no", "off"}
_SKIP_COMMANDS: set[str] = {
    "changepassword",
    "collectstatic",
    "createsuperuser",
    "dbshell",
    "makemigrations",
    "migrate",
    "shell",
}

_lock = threading.Lock()
_has_run = False


def _command_from_argv(argv: Iterable[str]) -> str:
    argv = list(argv)
    return argv[1] if len(argv) > 1 else ""


def _auto_migrations_disabled() -> bool:
    flag = os.environ.get("PRINTER_GUI_AUTO_APPLY_MIGRATIONS", "1")
    return flag.strip().lower() in _DISABLE_VALUES


def _should_skip_for_command(command: str) -> bool:
    return command in _SKIP_COMMANDS


def ensure_migrations_applied() -> None:
    """Apply database migrations once per process."""
    global _has_run

    if _has_run or _auto_migrations_disabled():
        return

    with _lock:
        if _has_run:
            return

        if not apps.ready:
            # Ensure the Django app registry is populated before running migrations.
            import django

            django.setup()

        try:
            call_command("migrate", interactive=False, run_syncdb=True, verbosity=0)
        except Exception:  # pragma: no cover - surface unexpected errors
            logger.exception("Automatic migration application failed.")
            raise

        _has_run = True
        logger.info("Applied database migrations automatically.")


def maybe_apply_migrations(argv: Iterable[str] | None = None) -> None:
    """Apply migrations unless disabled or explicitly skipped for a command."""
    if _auto_migrations_disabled():
        return

    if argv is None:
        argv = sys.argv

    command = _command_from_argv(argv)
    if _should_skip_for_command(command):
        return

    ensure_migrations_applied()
