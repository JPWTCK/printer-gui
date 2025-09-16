"""Utility helpers for the printer application."""

from __future__ import annotations

from typing import Optional

from django.db import OperationalError, ProgrammingError

from .models import Settings


DEFAULT_APP_SETTINGS = {
    "app_title": "GUI Print Server",
    "default_color": "RGB",
    "default_orientation": "3",
    "printer_profile": "None found",
}


def get_app_settings() -> Optional[Settings]:
    """Return the singleton ``Settings`` instance if the table is ready."""

    try:
        app_settings, _ = Settings.objects.get_or_create(
            id=1,
            defaults=DEFAULT_APP_SETTINGS,
        )
    except (OperationalError, ProgrammingError):
        # The database might not be ready yet (e.g., during migrate).
        return None
    return app_settings
