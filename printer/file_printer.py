from django.conf import settings as django_settings

import subprocess as sp
import os
from .utils import DEFAULT_APP_SETTINGS, get_app_settings


UPLOADS_DIR = django_settings.STATICFILES_DIRS[0] + '/uploads/'
DEFAULT_PRINTER_PROFILE = DEFAULT_APP_SETTINGS["printer_profile"]


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

    if page_range == '0':
        command = [
            'lp', '-d', printer, '-o',
            ('orientation-requested=' + orientation),
            '-o', ('ColorModel=' + color), filename
        ]
    else:
        command = [
            'lp', '-d', printer, '-P', pages, '-o',
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
    abs_path = os.path.abspath(os.path.join(UPLOADS_DIR, filename))
    # Ensure the file is inside the uploads directory
    if not abs_path.startswith(os.path.abspath(UPLOADS_DIR)):
        return b"", b"Invalid filename: outside uploads directory"
    # Optionally, check file existence
    if not os.path.isfile(abs_path):
        return b"", b"Invalid filename: file does not exist"
    return print_pdf(abs_path, page_range, pages, color, orientation)
