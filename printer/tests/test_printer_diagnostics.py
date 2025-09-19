from __future__ import annotations
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from printer import file_printer


@dataclass
class _DummySettings:
    printer_profile: str

    def refresh_from_db(self) -> None:  # pragma: no cover - trivial helper
        return None


class PrinterDiagnosticsHelperTests(SimpleTestCase):
    def test_collects_state_and_supplies_from_pycups(self) -> None:
        dummy_settings = _DummySettings(printer_profile="Office_Printer")
        fake_connection = Mock()
        fake_connection.getPrinterAttributes.return_value = {
            "printer-state": 3,
            "printer-state-message": "Ready to print.",
            "marker-names": ["Black Toner", "Cyan Toner"],
            "marker-levels": ["70", "50"],
            "marker-colors": ["black", "cyan"],
        }
        fake_cups = SimpleNamespace(Connection=Mock(return_value=fake_connection))

        with patch("printer.file_printer.get_app_settings", return_value=dummy_settings), patch(
            "printer.file_printer.cups", fake_cups
        ):
            diagnostics = file_printer.get_printer_diagnostics()

        self.assertEqual(diagnostics["printer"], "Office_Printer")
        self.assertEqual(diagnostics["state"], "Idle")
        self.assertEqual(diagnostics["state_message"], "Ready to print.")
        self.assertEqual(
            diagnostics["supplies"],
            [
                {"name": "Black Toner", "level": 70, "color": "black"},
                {"name": "Cyan Toner", "level": 50, "color": "cyan"},
            ],
        )
        self.assertIsNone(diagnostics["error"])

    def test_returns_empty_supply_list_when_not_reported(self) -> None:
        dummy_settings = _DummySettings(printer_profile="Office_Printer")
        fake_connection = Mock()
        fake_connection.getPrinterAttributes.return_value = {
            "printer-state": "processing",
            "printer-state-message": ["Job 123 is running"],
        }
        fake_cups = SimpleNamespace(Connection=Mock(return_value=fake_connection))

        with patch("printer.file_printer.get_app_settings", return_value=dummy_settings), patch(
            "printer.file_printer.cups", fake_cups
        ):
            diagnostics = file_printer.get_printer_diagnostics()

        self.assertEqual(diagnostics["state"], "Processing")
        self.assertEqual(diagnostics["supplies"], [])
        self.assertIsNone(diagnostics["error"])

    def test_handles_failure_when_no_attributes_available(self) -> None:
        dummy_settings = _DummySettings(printer_profile="Office_Printer")
        fake_cups = SimpleNamespace(Connection=Mock(side_effect=RuntimeError("pycups unavailable")))

        with patch("printer.file_printer.get_app_settings", return_value=dummy_settings), patch(
            "printer.file_printer.cups", fake_cups
        ), patch("printer.file_printer._locate_ipptool_test_file", return_value="/tmp/ipptool"), patch(
            "printer.file_printer.sp.run", side_effect=FileNotFoundError("ipptool")
        ):
            diagnostics = file_printer.get_printer_diagnostics()

        self.assertEqual(diagnostics["printer"], "Office_Printer")
        self.assertEqual(diagnostics["error"], "Printer status unavailable")
        self.assertIsNone(diagnostics["state"])
        self.assertEqual(diagnostics["supplies"], [])
