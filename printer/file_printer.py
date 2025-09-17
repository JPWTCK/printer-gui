from django.conf import settings as django_settings

import subprocess as sp
import os
import re
from .utils import DEFAULT_APP_SETTINGS, get_app_settings


UPLOADS_DIR = django_settings.STATICFILES_DIRS[0] + '/uploads/'
_UPLOADS_ROOT = os.path.abspath(UPLOADS_DIR)
DEFAULT_PRINTER_PROFILE = DEFAULT_APP_SETTINGS["printer_profile"]

ALLOWED_COLORS = {"Gray", "RGB"}
ALLOWED_ORIENTATIONS = {"3", "4"}
ALLOWED_PAGE_RANGES = {"0", "1"}
_PRINTER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_PAGE_SELECTION_PATTERN = re.compile(r"^[0-9]+(?:[-,][0-9]+)*$")
_SAFE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_MAX_FILENAME_LENGTH = 255


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
    if filename.startswith('-'):
        return b"", b"Invalid filename: cannot start with '-'"
    if os.path.basename(filename) != filename:
        return b"", b"Invalid filename: must not contain path separators"
    if len(filename) > _MAX_FILENAME_LENGTH:
        return b"", b"Invalid filename: exceeds maximum length"
    if not _SAFE_FILENAME_PATTERN.fullmatch(filename):
        return b"", b"Invalid filename: contains unsafe characters"
    abs_path = os.path.abspath(os.path.join(UPLOADS_DIR, filename))
    # Ensure the file is inside the uploads directory
    try:
        if os.path.commonpath([abs_path, _UPLOADS_ROOT]) != _UPLOADS_ROOT:
            return b"", b"Invalid filename: outside uploads directory"
    except ValueError:
        return b"", b"Invalid filename: outside uploads directory"
    # Optionally, check file existence
    if not os.path.isfile(abs_path):
        return b"", b"Invalid filename: file does not exist"
    return print_pdf(abs_path, page_range, pages, color, orientation)
