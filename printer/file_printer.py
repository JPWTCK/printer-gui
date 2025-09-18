import os
import subprocess as sp
import re
from typing import List, Optional, Tuple

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


_printer_profile = None
_PRINTER_QUERY_TIMEOUT = 5


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
    output = print_proc.communicate()

    return output


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
