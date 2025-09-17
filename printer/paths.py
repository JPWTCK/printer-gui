"""Shared filesystem paths used by the printer application."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings as django_settings


# ``STATICFILES_DIRS`` is configured in ``printer.settings`` to point at the
# project level ``static`` directory.  All uploaded files live inside an
# ``uploads`` folder beneath this directory so that they can be served and
# cleaned up consistently regardless of which module is interacting with them.
UPLOADS_DIR = Path(django_settings.STATICFILES_DIRS[0]) / "uploads"


def ensure_uploads_dir_exists() -> Path:
    """Ensure the uploads directory exists before we attempt to use it."""

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOADS_DIR

