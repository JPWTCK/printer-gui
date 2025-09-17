from django.conf import settings as django_settings

import subprocess as sp
import os
import re
from typing import List, Optional, Tuple

from .utils import DEFAULT_APP_SETTINGS, get_app_settings


UPLOADS_DIR = django_settings.STATICFILES_DIRS[0] + '/uploads/'
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
    app_settings = get_app_settings()
    if app_settings is None:
        return DEFAULT_PRINTER_PROFILE

    app_settings.refresh_from_db()
    printer_name = sanitize_printer_name(app_settings.printer_profile)
    if printer_name is None:
        return DEFAULT_PRINTER_PROFILE

    available_printers = set(_collect_available_printers())
    if available_printers and printer_name not in available_printers:
        return DEFAULT_PRINTER_PROFILE

    return printer_name


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

    sanitized_pages = re.sub(r"\s+", "", pages or "")
    if page_range != '0':
        if not sanitized_pages or not _PAGE_SELECTION_PATTERN.fullmatch(sanitized_pages):
            return b"", b"Invalid page selection requested."

    if page_range == '0':
        command = [
            'lp', '-d', printer, '-o',
            ('orientation-requested=' + orientation),
            '-o', ('ColorModel=' + color), filename
        ]
    else:
        command = [
            'lp', '-d', printer, '-P', sanitized_pages, '-o',
            ('orientation-requested=' + orientation),
            '-o', ('ColorModel=' + color), filename
        ]

    print_proc = sp.Popen(command, stdout=sp.PIPE, stderr=sp.PIPE)
    output = print_proc.communicate()
    
    return output


def print_file(filename, page_range, pages, color, orientation):
    # Prevent filenames that could be interpreted as options or contain path traversal
    if not filename or filename.strip() == "":
        return b"", b"Invalid filename: cannot be empty"
    if filename.startswith('-'):
        return b"", b"Invalid filename: cannot start with '-'"
    if filename.startswith('.'):
        return b"", b"Invalid filename: cannot start with '.'"
    if os.path.basename(filename) != filename:
        return b"", b"Invalid filename: must not contain path separators"
    # Only allow filenames with alphanumerics and dot (no spaces, dashes, etc.)
    if not re.fullmatch(r"[A-Za-z0-9.]+", filename):
        return b"", b"Invalid filename: filename must only contain letters, numbers, or dots."
    abs_path = os.path.abspath(os.path.join(UPLOADS_DIR, filename))
    # Ensure the file is inside the uploads directory
    if not abs_path.startswith(os.path.abspath(UPLOADS_DIR)):
        return b"", b"Invalid filename: outside uploads directory"
    # Optionally, check file existence
    if not os.path.isfile(abs_path):
        return b"", b"Invalid filename: file does not exist"
    return print_pdf(abs_path, page_range, pages, color, orientation)
