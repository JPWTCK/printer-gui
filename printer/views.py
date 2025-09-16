from django.contrib import messages
from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.core.files.storage import FileSystemStorage
from django.views.decorators.cache import never_cache
from django.conf import settings as django_settings

from .models import *
from .forms import *
from . import file_printer
from .utils import DEFAULT_APP_SETTINGS, get_app_settings

import re
from pathlib import Path

ALLOWED_EXTENSIONS = {
    '.pdf', '.ps', '.txt', '.jpg', '.jpeg', '.png', '.gif', '.tif', '.tiff'
}


UPLOADS_DIR = django_settings.STATICFILES_DIRS[0] + '/uploads/'


@never_cache
def index(request):
    files = File.objects.all()
    context = { 'files': files }
    return render(request, 'index.html', context)


def upload_file(request):
    printer_selected = True
    app_settings = get_app_settings()

    if request.method != 'POST':
        if app_settings is not None:
            app_settings.refresh_from_db()
            if app_settings.printer_profile == DEFAULT_APP_SETTINGS['printer_profile']:
                printer_selected = False
        else:
            printer_selected = False

        form = FileUploadForm()
    else:
        fs_storage = FileSystemStorage(location=UPLOADS_DIR)
        upload = request.FILES['file_upload']

        ext = Path(upload.name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            messages.error(request, 'File type not supported')
            return HttpResponseRedirect(reverse('index'))

        filename = re.sub('[^a-zA-Z0-9.]', '-', upload.name)
        upload.name = filename

        # Get settings object to apply defaults to the new file object:
        default_color = DEFAULT_APP_SETTINGS['default_color']
        default_orientation = DEFAULT_APP_SETTINGS['default_orientation']

        if app_settings is not None:
            app_settings.refresh_from_db()
            default_color = app_settings.default_color or default_color
            default_orientation = app_settings.default_orientation or default_orientation

        filename = fs_storage.save(filename, upload)
        new_file = File(
            name=upload.name, page_range='0', pages='All',
            color=default_color,
            orientation=default_orientation
        )
        new_file.save()
        return HttpResponseRedirect(reverse('index'))

    context = { 'printer_selected': printer_selected, 'form': form }
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
        files = File.objects.all()
        
        errors = False
        for fileObj in files:
            output = file_printer.print_file(fileObj.name, fileObj.page_range,
                                fileObj.pages, fileObj.color, fileObj.orientation)
            err = output[1].decode()
            if err != '':
                errors = True
                messages.error(request, err)
            else:
                messages.info(request, f"Printing {fileObj.name}")
            
            fileObj.delete()

        if errors:
            return HttpResponse(status=500)
        else:
            messages.success(request, 'Jobs completed')
            return HttpResponse(status=204) # OK, Nothing to return
    return HttpResponse(status=403) # !POST forbidden


def edit_settings(request):
    app_settings = get_app_settings()
    if app_settings is not None:
        app_settings.refresh_from_db()

    if request.method != 'POST':
        if app_settings is None:
            form = SettingsForm(initial=DEFAULT_APP_SETTINGS)
        else:
            form = SettingsForm(instance=app_settings)
    else:
        if app_settings is None:
            form = SettingsForm(data=request.POST)
        else:
            form = SettingsForm(instance=app_settings, data=request.POST)

        form.save()
        file_printer.refresh_printer_profile()
        return HttpResponseRedirect(reverse('index'))

    context = { 'settings': app_settings, 'form': form }
    return render(request, 'settings.html', context)
