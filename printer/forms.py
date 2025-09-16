from __future__ import annotations

from typing import List, Sequence, Tuple

import subprocess

from django import forms

from crispy_forms.helper import FormHelper

from .models import Settings
from .utils import DEFAULT_APP_SETTINGS


class PrinterLookupError(RuntimeError):
    """Raised when available printer profiles cannot be determined."""


def fetch_printer_choices() -> Sequence[Tuple[str, str]]:
    """Return available printer profiles from the local CUPS installation."""

    try:
        result = subprocess.run(
            ["lpstat", "-a"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise PrinterLookupError("The CUPS 'lpstat' command is not available.") from exc
    except subprocess.CalledProcessError as exc:
        output = (exc.stderr or exc.stdout or "").strip()
        raise PrinterLookupError(output or "Unable to list printers via lpstat.") from exc

    printers: List[Tuple[str, str]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        printer_name = line.split(" accepting", 1)[0]
        printers.append((printer_name, printer_name))

    return printers


class PrintOptions:
    RANGE_OPTIONS = (
        ('0', 'All pages'),
        ('1', 'Custom range') 
    )
    COLOR_OPTIONS = (
        ('Gray', 'Grayscale'),
        ('RGB', 'Color')
    )
    ORIENTATION_OPTIONS = (
        ('3', 'Portrait'),
        ('4', 'Landscape')
    )


class FileUploadForm(forms.Form):
    file_upload = forms.FileField(
        label='Upload Document',
        required=True,
        help_text='Only pdf, ps, txt, jpg, jpeg, png, gif, and tiff are supported',
        widget=forms.FileInput(attrs={
            'multiple': False,
            'accept': 'application/pdf,application/postscript,text/plain,image/jpeg,image/png,image/gif,image/tiff'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-25 fs-400 ff-sans-normal'
        self.helper.field_class = 'col-75'
        self.helper.form_tag = False
    

class SettingsForm(forms.ModelForm):
    app_title = forms.CharField(label='App title')
    default_color = forms.ChoiceField(
        label='Color default',
        choices=PrintOptions.COLOR_OPTIONS,
    )
    default_orientation = forms.ChoiceField(
        label='Orientation default',
        choices=PrintOptions.ORIENTATION_OPTIONS,
    )
    printer_profile = forms.ChoiceField(
        label='Printer Profile',
        choices=(),
        required=False,
    )

    class Meta:
        model = Settings
        fields = [
            'app_title',
            'default_color',
            'default_orientation',
            'printer_profile',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-25 fs-400 ff-sans-normal'
        self.helper.field_class = 'col-75'
        self.helper.form_tag = False

        self.printer_message = None

        try:
            printer_choices = list(fetch_printer_choices())
        except PrinterLookupError as exc:
            printer_choices = []
            self.printer_message = (
                'error',
                str(exc),
            )
        else:
            if not printer_choices:
                self.printer_message = (
                    'warning',
                    'No printers were detected. Confirm that the CUPS service is running.',
                )

        default_value = DEFAULT_APP_SETTINGS['printer_profile']
        default_choice = (default_value, 'No printer configured')
        if all(value != default_value for value, _ in printer_choices):
            printer_choices.append(default_choice)

        self.fields['printer_profile'].choices = printer_choices

