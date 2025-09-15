from . import settings
from .models import Settings

import subprocess as sp


UPLOADS_DIR = settings.STATICFILES_DIRS[0] + '/uploads/'


settings = Settings.objects.get(id=1)
printer = settings.printer_profile


def refresh_printer_profile():
    global printer
    settings.refresh_from_db()
    printer = settings.printer_profile


def print_pdf(filename, page_range, pages, color, orientation):
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
    global printer

    return print_pdf(UPLOADS_DIR + filename, page_range, pages, color, orientation)
