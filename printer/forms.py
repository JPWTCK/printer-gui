from django import forms

from crispy_forms.helper import FormHelper

from .file_printer import get_available_printer_profiles
from .models import Settings
from .upload_types import build_accept_attribute, describe_supported_extensions


def _build_horizontal_helper() -> FormHelper:
    helper = FormHelper()
    helper.form_class = 'form-horizontal'
    helper.label_class = 'col-25 fs-400 ff-sans-normal'
    helper.field_class = 'col-75'
    helper.form_tag = False
    return helper


class PrintOptions:
    RANGE_OPTIONS = (
        ('0', 'All pages'),
        ('1', 'Custom range'),
    )
    COLOR_OPTIONS = (
        ('Gray', 'Grayscale'),
        ('RGB', 'Color'),
    )
    ORIENTATION_OPTIONS = (
        ('3', 'Portrait'),
        ('4', 'Landscape'),
    )


class FileUploadForm(forms.Form):
    file_upload = forms.FileField(
        label='Upload Document',
        required=True,
        help_text=f'Supported formats: {describe_supported_extensions()}',
        widget=forms.FileInput(attrs={
            'multiple': False,
            'accept': build_accept_attribute(),
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = _build_horizontal_helper()
    

class SettingsForm(forms.ModelForm):
    app_title = forms.CharField(
        label='App title',
    )
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
        current_selection = self.initial.get('printer_profile') or getattr(
            self.instance,
            'printer_profile',
            None,
        )
        self.fields['printer_profile'].choices = get_available_printer_profiles(
            current_selection
        )
        self.helper = _build_horizontal_helper()

