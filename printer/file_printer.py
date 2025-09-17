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


def _resolve_path_within_uploads(filename, *, require_exists=True, not_found_message=None):
    """Resolve *filename* to a path within the uploads directory.

    Parameters
    ----------
    filename: path-like
        File name to resolve. Only plain filenames without path separators are
        accepted.
    require_exists: bool
        When ``True`` the path must exist. Missing paths produce
        *not_found_message*.
    not_found_message: Optional[bytes]
        Error message to use when the file cannot be located. When omitted a
        generic message suitable for filename validation is used.

    Returns
    -------
    Tuple[Path, Optional[bytes]]
        The resolved path and ``None`` on success; otherwise ``None`` and an
        error message.
    """

    uploads_dir_path = Path(UPLOADS_DIR)

    try:
        uploads_base = uploads_dir_path.resolve(strict=True)
    except FileNotFoundError:
        return None, b"Uploads directory is unavailable."
    except (OSError, RuntimeError):
        return None, b"Invalid filename: path resolution failed"

    if uploads_base == uploads_base.anchor:
        return None, b"Uploads directory is misconfigured."

    if not uploads_base.is_dir():
        return None, b"Uploads directory is unavailable."

    try:
        filename_to_resolve = os.fspath(filename)
    except (TypeError, ValueError):
        return None, b"Invalid filename: path resolution failed"

    filename_to_resolve = filename_to_resolve.strip()
    if not filename_to_resolve:
        return None, b"Invalid filename: path resolution failed"

    prospective_path = Path(filename_to_resolve)
    if prospective_path.is_absolute():
        return None, b"Invalid filename: outside uploads directory"

    if filename_to_resolve in {".", ".."}:
        return None, b"Invalid filename: outside uploads directory"

    for separator in (os.sep, os.altsep):
        if separator and separator in filename_to_resolve:
            return None, b"Invalid filename: outside uploads directory"

    if not _SAFE_FILENAME_PATTERN.fullmatch(filename_to_resolve):
        return None, b"Invalid filename: contains unsupported characters"

    resolved_path = None

    if require_exists:
        try:
            for candidate in uploads_base.iterdir():
                if candidate.name == filename_to_resolve:
                    resolved_path = candidate
                    break
        except (OSError, RuntimeError):
            return None, b"Invalid filename: path resolution failed"

        if resolved_path is None:
            message = not_found_message or b"Invalid filename: file does not exist"
            return None, message

        try:
            if resolved_path.is_symlink() or not resolved_path.is_file():
                message = not_found_message or b"Invalid filename: file does not exist"
                return None, message
        except OSError:
            return None, b"Invalid filename: path resolution failed"
    else:
        resolved_path = uploads_base / filename_to_resolve

    return resolved_path, None


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


def _run_print_command(resolved_path, printer, *, pages, color, orientation):
    command = [
        _LP_COMMAND,
        '-d', printer,
        '-o', f'orientation-requested={orientation}',
        '-o', f'ColorModel={color}',
    ]

    if pages is not None:
        command.extend(['-P', pages])

    command.append('-')

    try:
        with resolved_path.open('rb') as printable:
            completed = sp.run(
                command,
                check=False,
                capture_output=True,
                stdin=printable,
            )
    except FileNotFoundError:
        return b"", b"File to print does not exist."
    except OSError as exc:
        return b"", f"Failed to execute print command: {exc}".encode()

    return completed.stdout, completed.stderr


def print_pdf(filename, page_range, pages, color, orientation):
    if _LP_COMMAND is None:
        return b"", b"Printing is unavailable: 'lp' command not found."

    resolved_path, error = _resolve_path_within_uploads(
        filename,
        require_exists=True,
        not_found_message=b"File to print does not exist.",
    )
    if error is not None:
        return b"", error

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
    else:
        sanitized_pages = None

    return _run_print_command(
        resolved_path,
        printer,
        pages=sanitized_pages,
        color=color,
        orientation=orientation,
    )


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

    return print_pdf(sanitized_name, page_range, pages, color, orientation)
