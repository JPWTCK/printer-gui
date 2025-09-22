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
        ), patch(
            "printer.file_printer._query_printer_attributes_via_ipptool",
            return_value=(None, file_printer._PRINTER_STATUS_UNAVAILABLE),
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
        ), patch(
            "printer.file_printer._query_printer_attributes_via_ipptool",
            return_value=(None, file_printer._PRINTER_STATUS_UNAVAILABLE),
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
            "-X",
            "-T",
            str(file_printer._PRINTER_QUERY_TIMEOUT),
            "ipp://localhost/printers/Office_Printer",
            "/tmp/ipptool",
        ]
        expected_supplies = [
            {"name": "Black Cartridge", "level": 100, "color": "black"},
            {"name": "Cyan Cartridge", "level": 50, "color": "cyan"},
        ]

        ipptool_xml = """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<ipp:message xmlns:ipp=\"urn:ietf:params:xml:ns:ipp\">
  <ipp:attribute-group tag=\"printer-attributes-tag\">
    <ipp:attribute name=\"printer-state\" tag=\"enum\">
      <ipp:value>processing</ipp:value>
    </ipp:attribute>
    <ipp:attribute name=\"printer-state-message\" tag=\"textWithoutLanguage\">
      <ipp:value>Printing job 123</ipp:value>
    </ipp:attribute>
    <ipp:attribute name=\"marker-names\" tag=\"nameWithoutLanguage\">
      <ipp:value>Black Cartridge</ipp:value>
      <ipp:value>Cyan Cartridge</ipp:value>
    </ipp:attribute>
    <ipp:attribute name=\"marker-levels\" tag=\"integer\">
      <ipp:value>100</ipp:value>
      <ipp:value>50</ipp:value>
    </ipp:attribute>
    <ipp:attribute name=\"marker-colors\" tag=\"nameWithoutLanguage\">
      <ipp:value>black</ipp:value>
      <ipp:value>cyan</ipp:value>
    </ipp:attribute>
  </ipp:attribute-group>
</ipp:message>
"""

        ipptool_variants = {
            "xml_only": ipptool_xml,
            "xml_with_trailing_metadata": ipptool_xml
            + "\n\"/usr/share/cups/ipptool/get-printer-attributes.test\":\n"
            + "Get printer attributes using get-printer-attributes                  [PASS]\n",
        }

        for variant, ipptool_stdout in ipptool_variants.items():
            with self.subTest(ipptool_output=variant):
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

    def test_collects_state_and_marker_supplies_from_ipptool_plist_output(self) -> None:
        dummy_settings = _DummySettings(printer_profile="Office_Printer")
        expected_command = [
            "ipptool",
            "-X",
            "-T",
            str(file_printer._PRINTER_QUERY_TIMEOUT),
            "ipp://localhost/printers/Office_Printer",
            "/tmp/ipptool",
        ]
        expected_supplies = [
            {"name": "Black Cartridge", "level": 100, "color": "black"},
            {"name": "Cyan Cartridge", "level": 50, "color": "cyan"},
        ]

        ipptool_plist = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
  <key>ResponseAttributes</key>
  <array>
    <dict>
      <key>group-tag</key>
      <string>printer-attributes-tag</string>
      <key>attributes</key>
      <array>
        <dict>
          <key>name</key>
          <string>printer-state</string>
          <key>value-tag</key>
          <string>enum</string>
          <key>values</key>
          <array>
            <dict>
              <key>value</key>
              <integer>4</integer>
            </dict>
          </array>
        </dict>
        <dict>
          <key>name</key>
          <string>printer-state-message</string>
          <key>value-tag</key>
          <string>textWithoutLanguage</string>
          <key>values</key>
          <array>
            <dict>
              <key>value</key>
              <string>Printing job 123</string>
            </dict>
          </array>
        </dict>
        <dict>
          <key>name</key>
          <string>marker-names</string>
          <key>value-tag</key>
          <string>nameWithoutLanguage</string>
          <key>values</key>
          <array>
            <dict>
              <key>value</key>
              <string>Black Cartridge</string>
            </dict>
            <dict>
              <key>value</key>
              <string>Cyan Cartridge</string>
            </dict>
          </array>
        </dict>
        <dict>
          <key>name</key>
          <string>marker-levels</string>
          <key>value-tag</key>
          <string>integer</string>
          <key>values</key>
          <array>
            <dict>
              <key>value</key>
              <integer>100</integer>
            </dict>
            <dict>
              <key>value</key>
              <integer>50</integer>
            </dict>
          </array>
        </dict>
        <dict>
          <key>name</key>
          <string>marker-colors</string>
          <key>value-tag</key>
          <string>nameWithoutLanguage</string>
          <key>values</key>
          <array>
            <dict>
              <key>value</key>
              <string>black</string>
            </dict>
            <dict>
              <key>value</key>
              <string>cyan</string>
            </dict>
          </array>
        </dict>
      </array>
    </dict>
  </array>
</dict>
</plist>
"""

        completed = sp.CompletedProcess(
            args=["ipptool"],
            returncode=0,
            stdout=ipptool_plist
            + "\n\"/usr/share/cups/ipptool/get-printer-attributes.test\":\n"
            + "Get printer attributes using get-printer-attributes                  [PASS]\n",
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
        self.assertIsNone(diagnostics["error"])

    def test_ipptool_metadata_only_falls_back_to_pycups(self) -> None:
        dummy_settings = _DummySettings(printer_profile="Office_Printer")
        fake_connection = Mock()
        fake_connection.getPrinterAttributes.return_value = {
            "printer-state": 3,
            "printer-state-message": "Ready",
            "marker-names": ["Black Toner"],
            "marker-levels": ["80"],
            "marker-colors": ["black"],
        }
        fake_cups = SimpleNamespace(Connection=Mock(return_value=fake_connection))

        metadata_only = (
            '"/usr/share/cups/ipptool/get-printer-attributes.test":\n'
            "Get printer attributes using get-printer-attributes                  [PASS]\n"
        )
        completed = sp.CompletedProcess(
            args=["ipptool"],
            returncode=0,
            stdout=metadata_only,
            stderr="",
        )

        expected_command = [
            "ipptool",
            "-X",
            "-T",
            str(file_printer._PRINTER_QUERY_TIMEOUT),
            "ipp://localhost/printers/Office_Printer",
            "/tmp/ipptool",
        ]

        with patch("printer.file_printer.get_app_settings", return_value=dummy_settings), patch(
            "printer.file_printer.cups", fake_cups
        ), patch(
            "printer.file_printer._locate_ipptool_test_file", return_value="/tmp/ipptool"
        ), patch("printer.file_printer.sp.run") as mock_run:
            mock_run.return_value = completed
            diagnostics = file_printer.get_printer_diagnostics()

        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args[0][0], expected_command)

        self.assertEqual(diagnostics["state"], "Idle")
        self.assertEqual(diagnostics["state_message"], "Ready")
        self.assertEqual(
            diagnostics["supplies"], [{"name": "Black Toner", "level": 80, "color": "black"}]
        )
        self.assertIsNone(diagnostics["error"])
