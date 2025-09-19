from __future__ import annotations

import subprocess as sp
from dataclasses import dataclass
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from printer import file_printer


@dataclass
class _DummySettings:
    printer_profile: str

    def refresh_from_db(self) -> None:  # pragma: no cover - trivial test helper
        return None


class PrinterStatusHelperTests(SimpleTestCase):
    def test_helper_parses_idle_status(self) -> None:
        dummy_settings = _DummySettings(printer_profile="Office_Printer")
        lpstat_output = "printer Office_Printer is idle.  enabled since Tue 01 Jan 2021 10:00:00 AM"

        with patch("printer.file_printer.get_app_settings", return_value=dummy_settings), patch(
            "printer.file_printer.sp.run",
            return_value=sp.CompletedProcess(
                ["lpstat", "-p", "Office_Printer"],
                0,
                stdout=lpstat_output,
                stderr="",
            ),
        ):
            status = file_printer.get_printer_status()

        self.assertEqual(status, "Idle")

    def test_helper_returns_error_output_when_available(self) -> None:
        lpstat_error = "lpstat: Printer not found"

        with patch(
            "printer.file_printer.sp.run",
            return_value=sp.CompletedProcess(
                ["lpstat", "-p", "Missing_Printer"],
                1,
                stdout="",
                stderr=lpstat_error,
            ),
        ):
            status = file_printer.get_printer_status("Missing_Printer")

        self.assertEqual(status, lpstat_error)

    def test_helper_handles_timeout(self) -> None:
        with patch(
            "printer.file_printer.sp.run",
            side_effect=sp.TimeoutExpired(cmd=["lpstat", "-p", "Office_Printer"], timeout=5),
        ):
            status = file_printer.get_printer_status("Office_Printer")

        self.assertEqual(status, "Printer status check timed out")


class IndexViewPrinterStatusTests(TestCase):
    def test_index_includes_printer_status(self) -> None:
        with patch("printer.views.file_printer.get_printer_status", return_value="Printer status unavailable"):
            response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["printer_status"], "Printer status unavailable")


class PrinterDiagnosticsTests(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.dummy_settings = _DummySettings(printer_profile="Office_Printer")

    def test_diagnostics_use_lpstat_state_when_attributes_missing(self) -> None:
        with patch("printer.file_printer.get_app_settings", return_value=self.dummy_settings), patch(
            "printer.file_printer._query_printer_attributes_via_pycups",
            return_value=(None, file_printer._PRINTER_STATUS_UNAVAILABLE),
        ), patch(
            "printer.file_printer._query_printer_attributes_via_ipptool",
            return_value=(None, file_printer._PRINTER_STATUS_UNAVAILABLE),
        ), patch(
            "printer.file_printer._query_printer_state_via_lpstat",
            return_value=("Idle", None),
        ):
            diagnostics = file_printer.get_printer_diagnostics()

        self.assertEqual(diagnostics["state"], "Idle")
        self.assertIsNone(diagnostics["error"])

    def test_diagnostics_report_lpstat_error_when_no_state_available(self) -> None:
        with patch("printer.file_printer.get_app_settings", return_value=self.dummy_settings), patch(
            "printer.file_printer._query_printer_attributes_via_pycups",
            return_value=(None, None),
        ), patch(
            "printer.file_printer._query_printer_attributes_via_ipptool",
            return_value=(None, None),
        ), patch(
            "printer.file_printer._query_printer_state_via_lpstat",
            return_value=(None, file_printer._PRINTER_STATUS_TIMEOUT),
        ):
            diagnostics = file_printer.get_printer_diagnostics()

        self.assertIsNone(diagnostics["state"])
        self.assertEqual(diagnostics["error"], file_printer._PRINTER_STATUS_TIMEOUT)
