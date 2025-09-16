import re
from pathlib import Path

from django.conf import settings as django_settings
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from . import file_printer
from .forms import FileUploadForm, SettingsForm
from .models import File
from .utils import DEFAULT_APP_SETTINGS, get_app_settings

ALLOWED_EXTENSIONS = {
    '.pdf',
    '.ps',
    '.txt',
    '.jpg',
    '.jpeg',
    '.png',
    '.gif',
    '.tif',
    '.tiff',
}


UPLOADS_ROOT = Path(django_settings.MEDIA_ROOT) / 'uploads'


@never_cache
def index(request):
    files = File.objects.all()
    context = { 'files': files }
    return render(request, 'index.html', context)


def upload_file(request):
    app_settings = get_app_settings()
    printer_selected = True

    if app_settings is None:
        printer_selected = False
    else:
        app_settings.refresh_from_db()
        if app_settings.printer_profile == DEFAULT_APP_SETTINGS['printer_profile']:
            printer_selected = False

    if request.method == 'POST':
        form = FileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            upload = form.cleaned_data['file_upload']
            ext = Path(upload.name).suffix.lower()
            if ext not in ALLOWED_EXTENSIONS:
                messages.error(request, 'File type not supported')
                return HttpResponseRedirect(reverse('index'))

            filename = re.sub(r'[^a-zA-Z0-9.]', '-', upload.name)
            storage = FileSystemStorage(location=str(UPLOADS_ROOT))
            stored_name = storage.save(filename, upload)

            default_color = DEFAULT_APP_SETTINGS['default_color']
            default_orientation = DEFAULT_APP_SETTINGS['default_orientation']

            if app_settings is not None:
                default_color = app_settings.default_color or default_color
                default_orientation = app_settings.default_orientation or default_orientation

            File.objects.create(
                name=stored_name,
                page_range='0',
                pages='All',
                color=default_color,
                orientation=default_orientation,
            )
            return HttpResponseRedirect(reverse('index'))

        messages.error(request, 'Please correct the errors below.')
    else:
        form = FileUploadForm()

    context = {'printer_selected': printer_selected, 'form': form}
    return render(request, 'upload_file.html', context)


def edit_file(request, file_id):
    fileObj = File.objects.get(id=file_id)
    fileObj.refresh_from_db()
    context = { 'file': fileObj }
    return render(request, 'edit_file.html', context)


def submit_edit_file_form(request):
    if request.method == 'POST':
        fileObj = File.objects.get(id=int(request.POST['file_id']))
        fileObj.name = request.POST['name']
        fileObj.page_range = request.POST['page_range']
        fileObj.pages = request.POST['pages']
        fileObj.color = request.POST['color']
        fileObj.orientation = request.POST['orientation']
        fileObj.save()
        return HttpResponse(status=200)
    else:
        return HttpResponse(status=403)


def delete_file(request, file_id):
    fileObj = File.objects.get(id=file_id)
    fileObj.delete()
    
    return HttpResponseRedirect(reverse('index'))


def print_files(request):
    if request.method == 'POST':
        files = list(File.objects.all())

        errors = False
        any_success = False
        for fileObj in files:
            _stdout, stderr = file_printer.print_file(
                fileObj.name,
                fileObj.page_range,
                fileObj.pages,
                fileObj.color,
                fileObj.orientation,
            )
            err = stderr.decode('utf-8', errors='replace').strip()
            if err:
                errors = True
                messages.error(request, err)
                continue

            any_success = True
            messages.info(request, f"Printing {fileObj.name}")
            fileObj.delete()

        if errors:
            return HttpResponse(status=500)

        if any_success:
            messages.success(request, 'Jobs completed')
        return HttpResponse(status=204) # OK, Nothing to return
    return HttpResponse(status=403) # !POST forbidden


def edit_settings(request):
    app_settings = get_app_settings()
    if app_settings is not None:
        app_settings.refresh_from_db()

    form_kwargs = {}
    if app_settings is None:
        form_kwargs['initial'] = DEFAULT_APP_SETTINGS
    else:
        form_kwargs['instance'] = app_settings

    if request.method == 'POST':
        form = SettingsForm(data=request.POST, **form_kwargs)
        if form.is_valid():
            form.save()
            file_printer.refresh_printer_profile()
            messages.success(request, 'Settings updated successfully.')
            return HttpResponseRedirect(reverse('index'))

        messages.error(request, 'Please correct the errors below.')
    else:
        form = SettingsForm(**form_kwargs)

    printer_message = getattr(form, 'printer_message', None)
    if printer_message:
        level, message_text = printer_message
        if level == 'error':
            messages.error(request, message_text)
        else:
            messages.warning(request, message_text)

    context = {'settings': app_settings, 'form': form}
    return render(request, 'settings.html', context)
