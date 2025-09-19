import os
import re
import subprocess as sp
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

    try:
        result = sp.run(
            ["lpstat", "-p", sanitized],
            check=False,
            stdout=sp.PIPE,
            stderr=sp.PIPE,
            text=True,
            timeout=_PRINTER_QUERY_TIMEOUT,
        )
    except sp.TimeoutExpired:
        return _PRINTER_STATUS_TIMEOUT
    except (OSError, ValueError):
        return _PRINTER_STATUS_UNAVAILABLE

    status = _parse_lpstat_result(result, sanitized)
    if status:
        return status

    return _PRINTER_STATUS_UNAVAILABLE


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
        for component in re.split(r";\s*", raw_entry):
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


def _clean_ipptool_key(key: str) -> str:
    normalized = re.sub(r"[ \t\r\f\v]+", " ", key.strip())
    if "(" in normalized:
        normalized = normalized.split("(", 1)[0].rstrip()
    return normalized


def _clean_ipptool_value(value: str) -> str:
    cleaned = value.strip()
    if cleaned.endswith(","):
        cleaned = cleaned[:-1].rstrip()
    if (
        len(cleaned) >= 2
        and cleaned[0] == cleaned[-1]
        and cleaned[0] in {'"', "'"}
    ):
        cleaned = cleaned[1:-1]
    return cleaned


def _parse_ipptool_output(output: str) -> Dict[str, Any]:
    attributes: Dict[str, Any] = {}
    for raw_line in output.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        key: str
        value: str
        if ":" in stripped:
            raw_key, value = stripped.split(":", 1)
        elif "=" in stripped:
            raw_key, value = stripped.split("=", 1)
        else:
            continue

        key = _clean_ipptool_key(raw_key)
        value = _clean_ipptool_value(value)
        if not key:
            continue

        existing = attributes.get(key)
        if existing is None:
            attributes[key] = value
        else:
            if isinstance(existing, list):
                existing.append(value)
            else:
                attributes[key] = [existing, value]

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
            ["ipptool", "-T", str(_PRINTER_QUERY_TIMEOUT), uri, test_file],
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

    cups_attributes, cups_error = _query_printer_attributes_via_pycups(sanitized)
    if cups_attributes is not None:
        attributes = cups_attributes
    if cups_error:
        error_message = cups_error

    if attributes is None:
        ipptool_attributes, ipptool_error = _query_printer_attributes_via_ipptool(sanitized)
        if ipptool_attributes is not None:
            attributes = ipptool_attributes
            error_message = None
        elif ipptool_error:
            error_message = ipptool_error

    diagnostics["error"] = error_message

    if not attributes:
        return diagnostics

    state = _normalize_state(attributes.get("printer-state"))
    if state is None:
        state = _normalize_state(attributes.get("printer-state-reasons"))
    diagnostics["state"] = state
    diagnostics["state_message"] = _normalize_text(attributes.get("printer-state-message"))
    diagnostics["supplies"] = _parse_supply_entries(attributes)

    if diagnostics["error"] and diagnostics["state"]:
        diagnostics["error"] = None

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
