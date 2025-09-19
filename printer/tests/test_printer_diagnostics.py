from __future__ import annotations
from dataclasses import dataclass
import subprocess as sp
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

    def test_collects_state_and_marker_supplies_from_ipptool_output(self) -> None:
        dummy_settings = _DummySettings(printer_profile="Office_Printer")
        expected_command = [
            "ipptool",
            "-T",
            str(file_printer._PRINTER_QUERY_TIMEOUT),
            "ipp://localhost/printers/Office_Printer",
            "/tmp/ipptool",
        ]
        expected_supplies = [
            {"name": "Black Cartridge", "level": 100, "color": "black"},
            {"name": "Cyan Cartridge", "level": 50, "color": "cyan"},
        ]

        ipptool_variants = {
            "spaces": [
                '"ipp://localhost/printers/Office_Printer" - get-printer-attributes',
                "{",
                "    attributes-charset (charset) = utf-8",
                "    printer-state (enum) = processing",
                "    printer-state-message (textWithoutLanguage) = \"Printing job 123\"",
                "    marker-names (nameWithoutLanguage) = \"Black Cartridge\"",
                "    marker-names (nameWithoutLanguage) = \"Cyan Cartridge\"",
                "    marker-levels (integer) = 100",
                "    marker-levels (integer) = 50",
                "    marker-colors (nameWithoutLanguage) = \"black\"",
                "    marker-colors (nameWithoutLanguage) = \"cyan\"",
                "}",
            ],
            "tabs": [
                '"ipp://localhost/printers/Office_Printer" - get-printer-attributes',
                "{",
                "\tattributes-charset\t(charset) = utf-8",
                "\tprinter-state\t(enum) = processing",
                "\tprinter-state-message\t(textWithoutLanguage) = \"Printing job 123\"",
                "\tmarker-names\t(nameWithoutLanguage) = \"Black Cartridge\"",
                "\tmarker-names\t(nameWithoutLanguage) = \"Cyan Cartridge\"",
                "\tmarker-levels\t(integer) = 100",
                "\tmarker-levels\t(integer) = 50",
                "\tmarker-colors\t(nameWithoutLanguage) = \"black\"",
                "\tmarker-colors\t(nameWithoutLanguage) = \"cyan\"",
                "}",
            ],
        }

        for variant, lines in ipptool_variants.items():
            with self.subTest(ipptool_output=variant):
                ipptool_stdout = "\n".join(lines)
                completed = sp.CompletedProcess(
                    args=["ipptool"],
                    returncode=0,
                    stdout=ipptool_stdout,
                    stderr="",
                )

                with patch("printer.file_printer.get_app_settings", return_value=dummy_settings), patch(
                    "printer.file_printer.cups", None
                ), patch(
                    "printer.file_printer._locate_ipptool_test_file", return_value="/tmp/ipptool"
                ), patch("printer.file_printer.sp.run") as mock_run:
                    mock_run.return_value = completed
                    diagnostics = file_printer.get_printer_diagnostics()

                    mock_run.assert_called_once()
                    self.assertEqual(mock_run.call_args[0][0], expected_command)

                self.assertEqual(diagnostics["state"], "Processing")
                self.assertEqual(diagnostics["state_message"], "Printing job 123")
                self.assertEqual(diagnostics["supplies"], expected_supplies)
                self.assertNotEqual(
                    diagnostics["error"], file_printer._PRINTER_STATUS_UNAVAILABLE
                )
                self.assertIsNone(diagnostics["error"])
