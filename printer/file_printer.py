from django.conf import settings as django_settings

import subprocess as sp
import re
from pathlib import Path

from .utils import DEFAULT_APP_SETTINGS, get_app_settings


UPLOADS_DIR = Path(django_settings.STATICFILES_DIRS[0]) / 'uploads'
DEFAULT_PRINTER_PROFILE = DEFAULT_APP_SETTINGS["printer_profile"]

COLOR_MODELS = {"Gray": "Gray", "RGB": "RGB"}
ORIENTATION_OPTIONS = {"3": "3", "4": "4"}
ALLOWED_PAGE_RANGES = {"0", "1"}
_PRINTER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_PAGE_SELECTION_PATTERN = re.compile(r"^[0-9]+(?:[-,][0-9]+)*$")


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


def _resolve_print_path(filename):
    """Resolve and validate the path of an uploaded file."""

    try:
        candidate_path = Path(filename)
    except (TypeError, ValueError):
        return None, b"Invalid filename: must be a valid path"

    uploads_root = UPLOADS_DIR.resolve()

    if candidate_path.is_absolute():
        normalized_path = candidate_path
        base_name = candidate_path.name
    else:
        candidate_str = candidate_path.as_posix()
        if candidate_path.name != candidate_str:
            return None, b"Invalid filename: must not contain path separators"
        normalized_path = uploads_root / candidate_str
        base_name = candidate_str

    if base_name.startswith('-'):
        return None, b"Invalid filename: cannot start with '-'"

    try:
        resolved_path = normalized_path.resolve(strict=True)
    except FileNotFoundError:
        return None, b"Invalid filename: file does not exist"
    except (OSError, RuntimeError):
        return None, b"Invalid filename"

    try:
        resolved_path.relative_to(uploads_root)
    except ValueError:
        return None, b"Invalid filename: outside uploads directory"

    if not resolved_path.is_file():
        return None, b"Invalid filename: not a file"

    return resolved_path, None


def _execute_print_job(filename, page_range, pages, color, orientation):
    printer = _get_printer_profile()
    if not printer or printer == DEFAULT_PRINTER_PROFILE:
        error_message = "Printer profile is not configured.".encode()
        return b"", error_message

    if not _PRINTER_NAME_PATTERN.fullmatch(printer):
        return b"", b"Invalid printer profile configured."

    if color not in COLOR_MODELS:
        return b"", b"Invalid color option requested."

    if orientation not in ORIENTATION_OPTIONS:
        return b"", b"Invalid orientation option requested."

    if page_range not in ALLOWED_PAGE_RANGES:
        return b"", b"Invalid page range selection requested."

    sanitized_pages = re.sub(r"\s+", "", pages or "")
    if page_range != '0':
        if not sanitized_pages or not _PAGE_SELECTION_PATTERN.fullmatch(sanitized_pages):
            return b"", b"Invalid page selection requested."

    file_path, error = _resolve_print_path(filename)
    if error is not None:
        return b"", error

    command = [
        'lp', '-d', printer,
        '-o', f'orientation-requested={ORIENTATION_OPTIONS[orientation]}',
        '-o', f'ColorModel={COLOR_MODELS[color]}'
    ]

    if page_range != '0':
        command.extend(['-P', sanitized_pages])

    try:
        with file_path.open('rb') as file_stream:
            print_proc = sp.Popen(
                command,
                stdin=file_stream,
                stdout=sp.PIPE,
                stderr=sp.PIPE
            )
            output = print_proc.communicate()
    except OSError:
        return b"", b"Unable to access file for printing."

    return output


def print_pdf(filename, page_range, pages, color, orientation):
    return _execute_print_job(filename, page_range, pages, color, orientation)


def print_file(filename, page_range, pages, color, orientation):
    return _execute_print_job(filename, page_range, pages, color, orientation)
