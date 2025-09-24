import os
import plistlib
import re
import subprocess as sp
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

try:  # pragma: no cover - optional dependency
    import cups
except ImportError:  # pragma: no cover - optional dependency
    cups = None  # type: ignore[assignment]

from .paths import UPLOADS_DIR
from .utils import DEFAULT_APP_SETTINGS, get_app_settings


UPLOADS_ROOT = os.path.abspath(str(UPLOADS_DIR))
DEFAULT_PRINTER_PROFILE = DEFAULT_APP_SETTINGS["printer_profile"]

ALLOWED_COLORS = {"Gray", "RGB"}
ALLOWED_ORIENTATIONS = {"3", "4"}
ALLOWED_PAGE_RANGES = {"0", "1"}
_PRINTER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_PAGE_SELECTION_PATTERN = re.compile(r"^[0-9]+(?:[-,][0-9]+)*$")
_SAFE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")

_PRINTER_STATUS_UNAVAILABLE = "Printer status unavailable"
_PRINTER_STATUS_TIMEOUT = "Printer status check timed out"
_PRINTER_NOT_SELECTED = "No printer selected"


_printer_profile = None
_PRINTER_QUERY_TIMEOUT = 5
_IPP_XML_NAMESPACE = "urn:ietf:params:xml:ns:ipp"
_IPP_XML_PREFIX = f"{{{_IPP_XML_NAMESPACE}}}"

_IPP_STATE_NAMES = {
    3: "Idle",
    4: "Processing",
    5: "Stopped",
}
_KNOWN_STATE_LABELS = {value.lower(): value for value in _IPP_STATE_NAMES.values()}

_IPPTOOL_TEST_FILES = (
    "/usr/share/cups/ipptool/get-printer-attributes.test",
    "/usr/local/share/cups/ipptool/get-printer-attributes.test",
)


def sanitize_printer_name(printer_name: Optional[str]) -> Optional[str]:
    """Return a safe printer name or ``None`` if the value is unsafe."""

    if printer_name is None:
        return None

    sanitized = printer_name.strip()
    if not sanitized or sanitized == DEFAULT_PRINTER_PROFILE:
        return None

    if not _PRINTER_NAME_PATTERN.fullmatch(sanitized):
        return None

    if sanitized.startswith('-'):
        return None

    return sanitized


def _collect_available_printers() -> List[str]:
    """Return a list of sanitized printer names reported by CUPS."""

    try:
        result = sp.run(
            ['lpstat', '-a'],
            check=False,
            stdout=sp.PIPE,
            stderr=sp.PIPE,
            text=True,
            timeout=_PRINTER_QUERY_TIMEOUT,
        )
    except (OSError, ValueError, sp.TimeoutExpired):
        return []

    printers: List[str] = []
    for line in result.stdout.splitlines():
        candidate = line.split(' accepting', 1)[0].strip()
        sanitized = sanitize_printer_name(candidate)
        if sanitized and sanitized not in printers:
            printers.append(sanitized)

    return printers


def get_printer_status(printer_name: Optional[str] = None) -> str:
    """Return a concise status string for the configured printer."""

    if printer_name is None:
        app_settings = get_app_settings()
        if app_settings is not None:
            app_settings.refresh_from_db()
            printer_name = app_settings.printer_profile

    sanitized = sanitize_printer_name(printer_name)
    if sanitized is None:
        return _PRINTER_NOT_SELECTED

    status, error_message = _query_printer_state_via_lpstat(sanitized)
    if status is not None:
        return status
    if error_message is not None:
        return error_message

    return _PRINTER_STATUS_UNAVAILABLE


def _query_printer_state_via_lpstat(printer: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        result = sp.run(
            ["lpstat", "-p", printer],
            check=False,
            stdout=sp.PIPE,
            stderr=sp.PIPE,
            text=True,
            timeout=_PRINTER_QUERY_TIMEOUT,
        )
    except sp.TimeoutExpired:
        return None, _PRINTER_STATUS_TIMEOUT
    except (OSError, ValueError):
        return None, _PRINTER_STATUS_UNAVAILABLE

    parsed = _parse_lpstat_result(result, printer)
    if parsed:
        if result.returncode == 0:
            return parsed, None
        return None, parsed

    returncode = getattr(result, "returncode", None)
    if returncode == 0:
        return None, None
    return None, _PRINTER_STATUS_UNAVAILABLE


def _parse_lpstat_result(result: sp.CompletedProcess[str], printer_name: str) -> Optional[str]:
    line = _first_nonempty_line(result.stdout)
    if line:
        parsed = _parse_lpstat_line(line, printer_name)
        if parsed:
            return parsed

    error_line = _first_nonempty_line(result.stderr)
    if error_line:
        return error_line

    if line:
        return line

    return None


def _first_nonempty_line(text: Optional[str]) -> Optional[str]:
    if not text:
        return None

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped:
            return re.sub(r"\s+", " ", stripped)

    return None


def _parse_lpstat_line(line: str, printer_name: str) -> Optional[str]:
    normalized = re.sub(r"\s+", " ", line).strip()
    prefix = f"printer {printer_name}"
    if normalized.lower().startswith(prefix.lower()):
        normalized = normalized[len(prefix) :].lstrip()

    if not normalized:
        return None

    primary = normalized.split(". ", 1)[0].rstrip(".")
    if primary.lower().startswith("is "):
        primary = primary[3:].strip()

    primary = primary.strip()
    if not primary:
        return None

    return primary[:1].upper() + primary[1:]


def _normalize_string(value: Any) -> Optional[str]:
    if value is None:
        return None

    if isinstance(value, str):
        stripped = value.strip()
    else:
        stripped = str(value).strip()

    if not stripped:
        return None

    return stripped


def _normalize_text(value: Any) -> Optional[str]:
    if isinstance(value, (list, tuple)):
        for item in value:
            normalized = _normalize_text(item)
            if normalized is not None:
                return normalized
        return None

    return _normalize_string(value)


def _normalize_state(value: Any) -> Optional[str]:
    if isinstance(value, (list, tuple)):
        for item in value:
            normalized = _normalize_state(item)
            if normalized is not None:
                return normalized
        return None

    if isinstance(value, int):
        return _IPP_STATE_NAMES.get(value, str(value))

    normalized = _normalize_string(value)
    if normalized is None:
        return None

    if normalized.isdigit():
        try:
            numeric = int(normalized)
        except ValueError:
            pass
        else:
            return _IPP_STATE_NAMES.get(numeric, str(numeric))

    lowered = normalized.lower()
    if lowered in _KNOWN_STATE_LABELS:
        return _KNOWN_STATE_LABELS[lowered]

    return normalized


def _ensure_list(value: Any) -> List[str]:
    if value is None:
        return []

    if isinstance(value, (list, tuple)):
        raw_values = list(value)
    else:
        raw_values = [value]

    normalized: List[str] = []
    for item in raw_values:
        if isinstance(item, str):
            candidate = item.strip()
            if candidate.startswith("[") and candidate.endswith("]"):
                candidate = candidate[1:-1]
            parts = re.split(r",\s*|;\s*", candidate)
        else:
            parts = [item]

        for part in parts:
            normalized_part = _normalize_string(part)
            if normalized_part is None:
                continue
            if (
                len(normalized_part) >= 2
                and normalized_part[0] == normalized_part[-1]
                and normalized_part[0] in {'"', "'"}
            ):
                normalized_part = normalized_part[1:-1]
            normalized.append(normalized_part)

    return normalized


def _parse_marker_level(value: str) -> Optional[int]:
    normalized = _normalize_string(value)
    if normalized is None:
        return None

    if re.fullmatch(r"-?\d+", normalized):
        try:
            return int(normalized)
        except ValueError:
            return None

    return None


def _parse_printer_supply(value: Any) -> List[Dict[str, Any]]:
    supplies: List[Dict[str, Any]] = []
    for raw_entry in _ensure_list(value):
        entry: Dict[str, Any] = {}
        components: List[Tuple[str, str]] = []

        if isinstance(raw_entry, dict):
            for raw_key, raw_val in raw_entry.items():
                normalized_key = _normalize_string(raw_key)
                if normalized_key is None:
                    continue
                normalized_key = normalized_key.lower()

                if isinstance(raw_val, (list, tuple)):
                    values = list(raw_val)
                else:
                    values = [raw_val]

                for value_item in values:
                    normalized_val = _normalize_string(value_item)
                    if normalized_val is None:
                        continue
                    if (
                        len(normalized_val) >= 2
                        and normalized_val[0] == normalized_val[-1]
                        and normalized_val[0] in {'"', "'"}
                    ):
                        normalized_val = normalized_val[1:-1]
                    components.append((normalized_key, normalized_val))
        else:
            normalized_entry = _normalize_string(raw_entry)
            if normalized_entry is None:
                continue
            for component in re.split(r";\s*", normalized_entry):
                if not component or "=" not in component:
                    continue
                key, raw_val = component.split("=", 1)
                normalized_val = _normalize_string(raw_val)
                if normalized_val is None:
                    continue
                if (
                    len(normalized_val) >= 2
                    and normalized_val[0] == normalized_val[-1]
                    and normalized_val[0] in {'"', "'"}
                ):
                    normalized_val = normalized_val[1:-1]

                normalized_key = key.strip().lower()
                components.append((normalized_key, normalized_val))

        for normalized_key, normalized_val in components:
            if normalized_key in {"marker-name", "supply-name"}:
                entry["name"] = normalized_val
            elif normalized_key in {"marker-color", "supply-color"}:
                entry["color"] = normalized_val
            elif normalized_key in {"marker-type", "supply-type"}:
                entry["type"] = normalized_val
            elif normalized_key in {"marker-level", "supply-level", "marker-levels"}:
                level = _parse_marker_level(normalized_val)
                entry["level"] = level if level is not None else normalized_val
            elif normalized_key in {"marker-state", "supply-state"}:
                entry["state"] = normalized_val

        if entry:
            supplies.append(entry)

    return supplies


def _parse_supply_entries(attributes: Dict[str, Any]) -> List[Dict[str, Any]]:
    marker_names = _ensure_list(attributes.get("marker-names"))
    if not marker_names:
        marker_names = _ensure_list(attributes.get("marker-name"))

    marker_levels = _ensure_list(attributes.get("marker-levels"))
    if not marker_levels:
        marker_levels = _ensure_list(attributes.get("marker-level"))

    marker_colors = _ensure_list(attributes.get("marker-colors"))
    if not marker_colors:
        marker_colors = _ensure_list(attributes.get("marker-color"))

    marker_states = _ensure_list(attributes.get("marker-state"))
    marker_types = _ensure_list(attributes.get("marker-types"))
    if not marker_types:
        marker_types = _ensure_list(attributes.get("marker-type"))

    total = max(
        len(marker_names),
        len(marker_levels),
        len(marker_colors),
        len(marker_states),
        len(marker_types),
    )

    supplies: List[Dict[str, Any]] = []
    for index in range(total):
        entry: Dict[str, Any] = {}
        if index < len(marker_names):
            entry["name"] = marker_names[index]
        if index < len(marker_colors):
            entry["color"] = marker_colors[index]
        if index < len(marker_types):
            entry["type"] = marker_types[index]
        if index < len(marker_levels):
            parsed_level = _parse_marker_level(marker_levels[index])
            entry["level"] = parsed_level if parsed_level is not None else marker_levels[index]
        if index < len(marker_states):
            entry["state"] = marker_states[index]
        if entry:
            supplies.append(entry)

    if supplies:
        return supplies

    return _parse_printer_supply(attributes.get("printer-supply"))


def _parse_ipptool_xml_collection(element: ET.Element) -> Dict[str, Any]:
    collection: Dict[str, Any] = {}
    for member in element.findall(f"{_IPP_XML_PREFIX}member"):
        member_name = member.get("name")
        if not member_name:
            continue

        values: List[Any] = []
        for value_element in member.findall(f"{_IPP_XML_PREFIX}value"):
            parsed_value = _parse_ipptool_xml_value(value_element)
            if parsed_value is None:
                continue
            if isinstance(parsed_value, list):
                values.extend(parsed_value)
            else:
                values.append(parsed_value)

        if not values:
            continue

        member_value: Any
        if len(values) == 1:
            member_value = values[0]
        else:
            member_value = values

        existing = collection.get(member_name)
        if existing is None:
            collection[member_name] = member_value
        else:
            if isinstance(existing, list):
                if isinstance(member_value, list):
                    existing.extend(member_value)
                else:
                    existing.append(member_value)
            else:
                if isinstance(member_value, list):
                    collection[member_name] = [existing, *member_value]
                else:
                    collection[member_name] = [existing, member_value]

    return collection


def _parse_ipptool_xml_value(element: ET.Element) -> Optional[Any]:
    collection = element.find(f"{_IPP_XML_PREFIX}collection")
    if collection is not None:
        parsed_collection = _parse_ipptool_xml_collection(collection)
        return parsed_collection if parsed_collection else None

    text = "".join(element.itertext()).strip()
    if not text:
        return None

    return text


def _merge_ipptool_attribute_values(
    attributes: Dict[str, Any],
    key: str,
    values: List[Any],
) -> None:
    if not values:
        return

    if key in attributes:
        existing = attributes[key]
        if isinstance(existing, list):
            existing.extend(values)
        else:
            attributes[key] = [existing, *values]
    else:
        if len(values) == 1:
            attributes[key] = values[0]
        else:
            attributes[key] = list(values)


def _parse_ipptool_xml_output(output: str) -> Dict[str, Any]:
    stripped_output = output.strip()
    if not stripped_output:
        return {}

    xml_start = stripped_output.find("<?xml")
    if xml_start == -1:
        xml_start = stripped_output.find("<ipp:")
    if xml_start == -1:
        return {}

    xml_text = stripped_output[xml_start:].strip()
    if not xml_text:
        return {}

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        end_index = xml_text.rfind("</ipp:")
        if end_index == -1:
            return {}
        end_close = xml_text.find(">", end_index)
        if end_close == -1:
            return {}
        try:
            root = ET.fromstring(xml_text[: end_close + 1])
        except ET.ParseError:
            return {}

    attributes: Dict[str, Any] = {}
    for attribute_element in root.findall(f".//{_IPP_XML_PREFIX}attribute"):
        name = attribute_element.get("name")
        if not name:
            continue

        values: List[Any] = []
        for value_element in attribute_element.findall(f"{_IPP_XML_PREFIX}value"):
            parsed_value = _parse_ipptool_xml_value(value_element)
            if parsed_value is None:
                continue
            if isinstance(parsed_value, list):
                values.extend(parsed_value)
            else:
                values.append(parsed_value)

        if not values:
            continue

        _merge_ipptool_attribute_values(attributes, name, values)

    return attributes


def _parse_ipptool_output(output: str) -> Dict[str, Any]:
    attributes = _parse_ipptool_xml_output(output)
    if attributes:
        return attributes

    return _parse_ipptool_plist_output(output)


def _plist_bool_to_string(value: bool) -> str:
    return "true" if value else "false"


def _parse_plist_scalar(value: Any) -> Optional[str]:
    if value is None:
        return None

    if isinstance(value, bool):
        return _plist_bool_to_string(value)

    return _normalize_string(value)


def _plist_to_list(value: Any) -> List[Any]:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def _parse_plist_collection(value: Any) -> Optional[Dict[str, Any]]:
    items: List[Any]
    if isinstance(value, dict):
        lower_keys = {str(key).lower(): key for key in value.keys()}
        for candidate in ("members", "member", "values"):
            key = lower_keys.get(candidate)
            if key is not None:
                items = _plist_to_list(value[key])
                break
        else:
            items = [
                {"name": key, "value": val}
                for key, val in value.items()
                if isinstance(key, str)
            ]
    else:
        items = _plist_to_list(value)

    collection: Dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict):
            continue

        lower_keys = {str(key).lower(): key for key in item.keys()}
        name_key = lower_keys.get("name")
        if name_key is None:
            continue
        member_name = _normalize_string(item[name_key])
        if not member_name:
            continue

        value_key = None
        for candidate in ("values", "value"):
            candidate_key = lower_keys.get(candidate)
            if candidate_key is not None:
                value_key = candidate_key
                break
        if value_key is None:
            continue

        member_values = _parse_plist_attribute_values(item[value_key])
        if not member_values:
            continue

        if len(member_values) == 1:
            member_value: Any = member_values[0]
        else:
            member_value = member_values

        existing = collection.get(member_name)
        if existing is None:
            collection[member_name] = member_value
        else:
            if isinstance(existing, list):
                if isinstance(member_value, list):
                    existing.extend(member_value)
                else:
                    existing.append(member_value)
            else:
                if isinstance(member_value, list):
                    collection[member_name] = [existing, *member_value]
                else:
                    collection[member_name] = [existing, member_value]

    return collection if collection else None


def _parse_plist_attribute_value(value: Any) -> Optional[Any]:
    if value is None:
        return None

    if isinstance(value, bool):
        return _plist_bool_to_string(value)

    if isinstance(value, (str, int, float)):
        return _normalize_string(value)

    if isinstance(value, bytes):
        return value

    if isinstance(value, list):
        values: List[Any] = []
        for item in value:
            parsed = _parse_plist_attribute_value(item)
            if parsed is None:
                continue
            if isinstance(parsed, list):
                values.extend(parsed)
            else:
                values.append(parsed)
        return values

    if isinstance(value, dict):
        lower_keys = {str(key).lower(): key for key in value.keys()}

        for scalar_key in ("text", "string", "integer", "real", "date"):
            key = lower_keys.get(scalar_key)
            if key is not None:
                return _parse_plist_scalar(value[key])

        if "boolean" in lower_keys:
            key = lower_keys["boolean"]
            boolean_value = value[key]
            if isinstance(boolean_value, bool):
                return _plist_bool_to_string(boolean_value)
            return _normalize_string(boolean_value)

        value_tag_key = lower_keys.get("value-tag")
        value_tag = _normalize_string(value[value_tag_key]) if value_tag_key else None
        if value_tag:
            value_tag = value_tag.lower()

        if value_tag == "collection":
            value_key = lower_keys.get("value") or lower_keys.get("values")
            if value_key is None:
                return None
            return _parse_plist_collection(value[value_key])

        if "values" in lower_keys:
            return _parse_plist_attribute_values(value[lower_keys["values"]])

        if "value" in lower_keys:
            return _parse_plist_attribute_value(value[lower_keys["value"]])

        if "data" in lower_keys:
            return value[lower_keys["data"]]

        if "name" in lower_keys:
            name = _normalize_string(value[lower_keys["name"]])
            if not name:
                return None
            nested_key = lower_keys.get("values") or lower_keys.get("value")
            if nested_key is None:
                return None
            nested_values = _parse_plist_attribute_values(value[nested_key])
            if not nested_values:
                return None
            if len(nested_values) == 1:
                return {name: nested_values[0]}
            return {name: nested_values}

        collection = _parse_plist_collection(value)
        if collection:
            return collection

    return None


def _parse_plist_attribute_values(value: Any) -> List[Any]:
    values: List[Any] = []
    for item in _plist_to_list(value):
        parsed = _parse_plist_attribute_value(item)
        if parsed is None:
            continue
        if isinstance(parsed, list):
            values.extend(parsed)
        else:
            values.append(parsed)
    return values


def _collect_plist_attributes(node: Any, attributes: Dict[str, Any]) -> None:
    if isinstance(node, dict):
        lower_keys = {str(key).lower(): key for key in node.keys()}

        name_key = lower_keys.get("name")
        value_key = None
        for candidate in ("values", "value"):
            candidate_key = lower_keys.get(candidate)
            if candidate_key is not None:
                value_key = candidate_key
                break

        if name_key is not None and value_key is not None:
            name = _normalize_string(node[name_key])
            if name:
                parsed_values = _parse_plist_attribute_values(node[value_key])
                if parsed_values:
                    _merge_ipptool_attribute_values(attributes, name, parsed_values)

            for key, value in node.items():
                if key in {name_key, value_key}:
                    continue
                if isinstance(value, (str, bytes, int, float, bool)):
                    continue
                _collect_plist_attributes(value, attributes)
            return

        for key, value in node.items():
            lower_key = str(key).lower()
            if lower_key.endswith("attributes") and lower_key != "attributes-count":
                if isinstance(value, dict):
                    for attribute_name, attribute_value in value.items():
                        normalized_name = _normalize_string(attribute_name)
                        if not normalized_name:
                            continue
                        parsed_values = _parse_plist_attribute_values(attribute_value)
                        if parsed_values:
                            _merge_ipptool_attribute_values(
                                attributes, normalized_name, parsed_values
                            )
                else:
                    _collect_plist_attributes(value, attributes)
            elif lower_key not in {"tag", "group-tag", "value-tag"}:
                normalized_name = _normalize_string(key)
                if normalized_name:
                    parsed_values = _parse_plist_attribute_values(value)
                    if parsed_values:
                        _merge_ipptool_attribute_values(
                            attributes, normalized_name, parsed_values
                        )
                        continue
                _collect_plist_attributes(value, attributes)

    elif isinstance(node, list):
        for item in node:
            _collect_plist_attributes(item, attributes)


def _parse_ipptool_plist_output(output: str) -> Dict[str, Any]:
    stripped_output = output.strip()
    if not stripped_output or "<plist" not in stripped_output:
        return {}

    if "ResponseAttributes" not in stripped_output:
        return {}

    xml_start = stripped_output.find("<?xml")
    plist_start = stripped_output.find("<plist")
    start_index = xml_start if xml_start != -1 else plist_start
    if start_index == -1:
        return {}

    plist_text = stripped_output[start_index:]
    end_index = plist_text.rfind("</plist>")
    if end_index != -1:
        plist_text = plist_text[: end_index + len("</plist>")]

    try:
        parsed_plist = plistlib.loads(plist_text.encode("utf-8"))
    except (plistlib.InvalidFileException, ValueError, AttributeError):
        return {}

    attributes: Dict[str, Any] = {}
    _collect_plist_attributes(parsed_plist, attributes)
    return attributes


def _locate_ipptool_test_file() -> Optional[str]:
    cups_datadir = os.environ.get("CUPS_DATADIR")
    if cups_datadir:
        candidate = os.path.join(cups_datadir, "ipptool", "get-printer-attributes.test")
        if os.path.isfile(candidate):
            return candidate

    for candidate in _IPPTOOL_TEST_FILES:
        if os.path.isfile(candidate):
            return candidate

    return None


def _query_printer_attributes_via_pycups(
    printer: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    cups_module = cups
    if not cups_module:
        return None, None

    try:
        connection = cups_module.Connection()
    except Exception:
        return None, _PRINTER_STATUS_UNAVAILABLE

    try:
        attributes = connection.getPrinterAttributes(printer)
    except Exception:
        return None, _PRINTER_STATUS_UNAVAILABLE

    if isinstance(attributes, dict):
        return attributes, None

    return None, _PRINTER_STATUS_UNAVAILABLE


def _query_printer_attributes_via_ipptool(
    printer: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    test_file = _locate_ipptool_test_file()
    if not test_file:
        return None, _PRINTER_STATUS_UNAVAILABLE

    uri = f"ipp://localhost/printers/{printer}"
    try:
        result = sp.run(
            ["ipptool", "-X", "-T", str(_PRINTER_QUERY_TIMEOUT), uri, test_file],
            check=False,
            stdout=sp.PIPE,
            stderr=sp.PIPE,
            text=True,
            timeout=_PRINTER_QUERY_TIMEOUT,
        )
    except sp.TimeoutExpired:
        return None, _PRINTER_STATUS_TIMEOUT
    except (OSError, ValueError):
        return None, _PRINTER_STATUS_UNAVAILABLE

    if result.returncode != 0:
        error_text = _first_nonempty_line(result.stderr) or _first_nonempty_line(result.stdout)
        return None, error_text or _PRINTER_STATUS_UNAVAILABLE

    attributes = _parse_ipptool_output(result.stdout)
    if not attributes and result.stderr:
        attributes = _parse_ipptool_output(result.stderr)
    if attributes:
        return attributes, None

    return None, _PRINTER_STATUS_UNAVAILABLE


def get_printer_diagnostics(printer_name: Optional[str] = None) -> Dict[str, Any]:
    diagnostics: Dict[str, Any] = {
        "printer": None,
        "state": None,
        "state_message": None,
        "supplies": [],
        "error": None,
    }

    if printer_name is None:
        app_settings = get_app_settings()
        if app_settings is not None:
            app_settings.refresh_from_db()
            printer_name = app_settings.printer_profile

    sanitized = sanitize_printer_name(printer_name)
    diagnostics["printer"] = sanitized

    if sanitized is None:
        diagnostics["error"] = _PRINTER_NOT_SELECTED
        return diagnostics

    attributes: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    ipptool_attributes, ipptool_error = _query_printer_attributes_via_ipptool(sanitized)
    if ipptool_attributes is not None:
        attributes = ipptool_attributes
    elif ipptool_error:
        error_message = ipptool_error

    if attributes is None:
        cups_attributes, cups_error = _query_printer_attributes_via_pycups(sanitized)
        if cups_attributes is not None:
            attributes = cups_attributes
            error_message = None
        elif cups_error and error_message in {None, _PRINTER_STATUS_UNAVAILABLE}:
            error_message = cups_error

    diagnostics["error"] = error_message

    if not attributes:
        status, status_error = _query_printer_state_via_lpstat(sanitized)
        if status is not None:
            diagnostics["state"] = status
            diagnostics["error"] = None
        elif status_error is not None and diagnostics["error"] in {None, _PRINTER_STATUS_UNAVAILABLE}:
            diagnostics["error"] = status_error
        return diagnostics

    state = _normalize_state(attributes.get("printer-state"))
    if state is None:
        state = _normalize_state(attributes.get("printer-state-reasons"))
    diagnostics["state"] = state
    diagnostics["state_message"] = _normalize_text(attributes.get("printer-state-message"))
    diagnostics["supplies"] = _parse_supply_entries(attributes)

    if diagnostics["error"] and diagnostics["state"]:
        diagnostics["error"] = None

    if diagnostics["state"] is None:
        status, status_error = _query_printer_state_via_lpstat(sanitized)
        if status is not None:
            diagnostics["state"] = status
            diagnostics["error"] = None
        elif status_error is not None and diagnostics["error"] in {None, _PRINTER_STATUS_UNAVAILABLE}:
            diagnostics["error"] = status_error

    return diagnostics


def get_available_printer_profiles(current_selection: Optional[str] = None) -> List[Tuple[str, str]]:
    """Return choices for printer profiles, including the current selection if needed."""

    printers = _collect_available_printers()
    current = sanitize_printer_name(current_selection)

    if current and current not in printers:
        printers.insert(0, current)

    if not printers:
        return [(DEFAULT_PRINTER_PROFILE, DEFAULT_PRINTER_PROFILE)]

    return [(printer, printer) for printer in printers]


def _load_printer_profile():
    available_printers = _collect_available_printers()

    app_settings = get_app_settings()
    if app_settings is None:
        printer_name = None
    else:
        app_settings.refresh_from_db()
        printer_name = sanitize_printer_name(app_settings.printer_profile)

    if printer_name and printer_name in available_printers:
        return printer_name

    if len(available_printers) == 1:
        return available_printers[0]

    return DEFAULT_PRINTER_PROFILE


def _get_printer_profile():
    global _printer_profile

    if _printer_profile is None:
        _printer_profile = _load_printer_profile()
    return _printer_profile


def refresh_printer_profile():
    global _printer_profile

    _printer_profile = _load_printer_profile()


def print_pdf(filename, page_range, pages, color, orientation):
    printer = _get_printer_profile()
    if not printer or printer == DEFAULT_PRINTER_PROFILE:
        error_message = "Printer profile is not configured.".encode()
        return b"", error_message

    printer = sanitize_printer_name(printer)
    if printer is None:
        return b"", b"Invalid printer profile configured."

    if color not in ALLOWED_COLORS:
        return b"", b"Invalid color option requested."

    if orientation not in ALLOWED_ORIENTATIONS:
        return b"", b"Invalid orientation option requested."

    if page_range not in ALLOWED_PAGE_RANGES:
        return b"", b"Invalid page range selection requested."

    if not isinstance(filename, str):
        return b"", b"Invalid file path provided."

    try:
        normalized_path = os.path.realpath(filename)
        uploads_common = os.path.commonpath([UPLOADS_ROOT, normalized_path])
    except (OSError, ValueError):
        return b"", b"Invalid file path provided."

    if uploads_common != UPLOADS_ROOT or not os.path.isfile(normalized_path):
        return b"", b"Invalid file path provided."

    sanitized_pages = re.sub(r"\s+", "", pages or "")
    if page_range != '0':
        if not sanitized_pages or not _PAGE_SELECTION_PATTERN.fullmatch(sanitized_pages):
            return b"", b"Invalid page selection requested."
        page_arguments: List[str] = ['-P', sanitized_pages]
    else:
        page_arguments = []

    color_option = {
        'Gray': 'ColorModel=Gray',
        'RGB': 'ColorModel=RGB',
    }[color]

    orientation_option = {
        '3': 'orientation-requested=3',
        '4': 'orientation-requested=4',
    }[orientation]

    command: List[str] = ['lp', '-d', printer]
    command.extend(page_arguments)
    command.extend(['-o', orientation_option, '-o', color_option, normalized_path])

    print_proc = sp.Popen(command, stdout=sp.PIPE, stderr=sp.PIPE)
    stdout, stderr = print_proc.communicate()

    if print_proc.returncode != 0:
        message_parts = []
        for stream in (stderr, stdout):
            if not stream:
                continue
            stripped = stream.strip()
            if stripped:
                message_parts.append(stripped)

        message_parts.append(
            f'Print command exited with status {print_proc.returncode}'.encode()
        )
        error_message = b"\n".join(message_parts)
        return stdout, error_message

    return stdout, stderr


def _resolve_upload_file_path(filename: str) -> Optional[str]:
    """Return an absolute path within ``UPLOADS_ROOT`` for a valid filename."""

    try:
        uploads_root = UPLOADS_ROOT
        with os.scandir(uploads_root) as entries:
            for entry in entries:
                if entry.name != filename:
                    continue
                try:
                    if not entry.is_file(follow_symlinks=False):
                        return None
                except OSError:
                    return None

                resolved_path = os.path.realpath(entry.path)
                try:
                    uploads_common = os.path.commonpath([uploads_root, resolved_path])
                except (OSError, ValueError):
                    return None

                if uploads_common != uploads_root:
                    return None

                if not os.path.isfile(resolved_path):
                    return None

                return resolved_path
    except OSError:
        return None

    return None


def print_file(filename, page_range, pages, color, orientation):
    if not isinstance(filename, str):
        return b"", b"Invalid filename: must be a string"

    candidate = filename.strip()
    if not candidate:
        return b"", b"Invalid filename: cannot be empty"

    if candidate.startswith('-'):
        return b"", b"Invalid filename: cannot start with '-'"

    if candidate.startswith('.'):
        return b"", b"Invalid filename: cannot start with '.'"

    if os.path.basename(candidate) != candidate:
        return b"", b"Invalid filename: must not contain path separators"

    if not _SAFE_FILENAME_PATTERN.fullmatch(candidate):
        return b"", b"Invalid filename: contains unsupported characters"

    resolved_path = _resolve_upload_file_path(candidate)
    if resolved_path is None:
        return b"", b"Invalid filename: file is not available for printing"

    return print_pdf(resolved_path, page_range, pages, color, orientation)
