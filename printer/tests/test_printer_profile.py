from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from unittest.mock import patch

from django.test import SimpleTestCase

from printer import file_printer


@dataclass
class _DummySettings:
    printer_profile: Optional[str]

    def refresh_from_db(self) -> None:  # pragma: no cover - behavior is trivial
        """Mimic the ``Settings`` model refresh for the test helpers."""
        # No-op for tests; the ``printer_profile`` attribute already holds the
        # up-to-date value we want to exercise.
        return None


class PrinterProfileSelectionTests(SimpleTestCase):
    def _load_profile_with(self, available: list[str], profile: Optional[str]):
        dummy_settings = _DummySettings(printer_profile=profile)
        with patch('printer.file_printer._collect_available_printers', return_value=available), patch(
            'printer.file_printer.get_app_settings', return_value=dummy_settings
        ):
            return file_printer._load_printer_profile()

    def test_single_available_printer_without_config_selects_printer(self) -> None:
        profile = self._load_profile_with(['Solo_Printer'], file_printer.DEFAULT_PRINTER_PROFILE)

        self.assertEqual(profile, 'Solo_Printer')

    def test_single_available_printer_when_database_unavailable(self) -> None:
        with patch('printer.file_printer._collect_available_printers', return_value=['Solo_Printer']), patch(
            'printer.file_printer.get_app_settings', return_value=None
        ):
            profile = file_printer._load_printer_profile()

        self.assertEqual(profile, 'Solo_Printer')

    def test_multiple_printers_still_require_explicit_selection(self) -> None:
        profile = self._load_profile_with(
            ['Office_Printer', 'Lab_Printer'],
            file_printer.DEFAULT_PRINTER_PROFILE,
        )

        self.assertEqual(profile, file_printer.DEFAULT_PRINTER_PROFILE)

    def test_existing_selection_is_respected_when_available(self) -> None:
        profile = self._load_profile_with(
            ['Office_Printer', 'Lab_Printer'],
            'Lab_Printer',
        )

        self.assertEqual(profile, 'Lab_Printer')
