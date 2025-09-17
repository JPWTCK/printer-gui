from django.conf import settings as django_settings

import subprocess as sp
import os
import re
from pathlib import Path
from shutil import which

from .utils import DEFAULT_APP_SETTINGS, get_app_settings


UPLOADS_DIR = Path(django_settings.STATICFILES_DIRS[0]) / 'uploads'
DEFAULT_PRINTER_PROFILE = DEFAULT_APP_SETTINGS["printer_profile"]

ALLOWED_COLORS = {"Gray", "RGB"}
ALLOWED_ORIENTATIONS = {"3", "4"}
ALLOWED_PAGE_RANGES = {"0", "1"}
_PRINTER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_PAGE_SELECTION_PATTERN = re.compile(r"^[0-9]+(?:[-,][0-9]+)*$")
_SAFE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9_.\- ]+$")

_LP_COMMAND = which("lp")


_printer_profile = None


def _load_printer_profile():
    app_settings = get_app_settings()
    if app_settings is None:
        return DEFAULT_PRINTER_PROFILE

    app_settings.refresh_from_db()
    printer_name = app_settings.printer_profile
    if not printer_name:
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
    if _LP_COMMAND is None:
        return b"", b"Printing is unavailable: 'lp' command not found."

    try:
        filename_to_print = os.fspath(filename)
    except TypeError:
        return b"", b"Invalid filename provided for printing."

    printer = _get_printer_profile()
    if not printer or printer == DEFAULT_PRINTER_PROFILE:
        error_message = "Printer profile is not configured.".encode()
        return b"", error_message

    if not _PRINTER_NAME_PATTERN.fullmatch(printer):
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

    if not os.path.isfile(filename_to_print):
        return b"", b"File to print does not exist."

    if page_range == '0':
        command = [
            _LP_COMMAND, '-d', printer, '-o',
            ('orientation-requested=' + orientation),
            '-o', ('ColorModel=' + color), filename_to_print
        ]
    else:
        command = [
            _LP_COMMAND, '-d', printer, '-P', sanitized_pages, '-o',
            ('orientation-requested=' + orientation),
            '-o', ('ColorModel=' + color), filename_to_print
        ]

    try:
        print_proc = sp.Popen(command, stdout=sp.PIPE, stderr=sp.PIPE)
        output = print_proc.communicate()
    except OSError as exc:
        return b"", f"Failed to execute print command: {exc}".encode()

    return output


def print_file(filename, page_range, pages, color, orientation):
    # Ensure filenames are non-empty plain strings to avoid surprises when
    # building the command arguments.
    if not isinstance(filename, str):
        return b"", b"Invalid filename: must be a string"

    sanitized_name = filename.strip()
    if not sanitized_name:
        return b"", b"Invalid filename: must not be empty"

    # Prevent filenames that could be interpreted as options or contain path traversal
    if sanitized_name.startswith('-'):
        return b"", b"Invalid filename: cannot start with '-'"
    if not _SAFE_FILENAME_PATTERN.fullmatch(sanitized_name):
        return b"", b"Invalid filename: contains unsupported characters"

    uploads_dir_path = Path(UPLOADS_DIR)

    try:
        base_path = uploads_dir_path.resolve(strict=False)
        candidate_path = (uploads_dir_path / sanitized_name).resolve(strict=False)
    except (OSError, RuntimeError):
        return b"", b"Invalid filename: path resolution failed"

    if not candidate_path.is_relative_to(base_path):
        return b"", b"Invalid filename: outside uploads directory"

    if not candidate_path.is_file():
        return b"", b"Invalid filename: file does not exist"

    return print_pdf(candidate_path, page_range, pages, color, orientation)
