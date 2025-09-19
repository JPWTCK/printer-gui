from django import forms
from .models import *

from .file_printer import get_available_printer_profiles
from .upload_types import build_accept_attribute, describe_supported_extensions

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Column

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
        help_text=f'Supported formats: {describe_supported_extensions()}',
        widget=forms.FileInput(attrs={
            'multiple': False,
            'accept': build_accept_attribute()
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class='form-horizontal'
        self.helper.label_class='col-25 fs-400 ff-sans-normal'
        self.helper.field_class='col-75'
        self.helper.form_tag = False
    

class SettingsForm(forms.ModelForm):
    app_title = forms.CharField(
        label = 'App title',
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
        fields = [ 'app_title', 'default_color', 'default_orientation',
                    'printer_profile' ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_selection = self.initial.get('printer_profile') or getattr(self.instance, 'printer_profile', None)
        self.fields['printer_profile'].choices = get_available_printer_profiles(current_selection)
        self.helper = FormHelper()
        self.helper.form_class='form-horizontal'
        self.helper.label_class='col-25 fs-400 ff-sans-normal'
        self.helper.field_class='col-75'
        self.helper.form_tag = False

