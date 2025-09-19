from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

import re
from pathlib import Path

from . import file_printer
from .conversion import ConversionError, convert_document_to_pdf
from .forms import FileUploadForm, PrintOptions, SettingsForm
from .models import File
from .paths import UPLOADS_DIR, ensure_uploads_dir_exists
from .upload_types import (
    CUPS_NATIVE_EXTENSIONS,
    SUPPORTED_UPLOAD_EXTENSIONS,
)
from .utils import DEFAULT_APP_SETTINGS, get_app_settings


def _ensure_session_key(request):
    session_key = request.session.session_key
    if session_key is None:
        request.session.create()
        session_key = request.session.session_key
    return session_key


def _claim_file_for_session(file_obj, session_key):
    if not file_obj.session_key:
        file_obj.session_key = session_key
        file_obj.save(update_fields=['session_key'])


def _claim_legacy_files(session_key):
    File.objects.filter(session_key='').update(session_key=session_key)


def _get_session_file(request, file_id):
    session_key = _ensure_session_key(request)
    file_obj = get_object_or_404(File, id=file_id)

    if file_obj.session_key and file_obj.session_key != session_key:
        raise Http404

    _claim_file_for_session(file_obj, session_key)
    return file_obj


def _sanitize_upload_name(upload_name: str) -> str:
    """Return a filesystem-safe filename that preserves the original suffix."""

    candidate = Path(upload_name)
    sanitized_stem = re.sub(r'[^A-Za-z0-9_-]+', '-', candidate.stem).strip('-_')
    if not sanitized_stem:
        sanitized_stem = 'upload'
    return f"{sanitized_stem}{candidate.suffix.lower()}"


@never_cache
def index(request):
    session_key = _ensure_session_key(request)
    _claim_legacy_files(session_key)

    files = File.objects.filter(session_key=session_key).order_by('-uploaded_at')
    printer_status = file_printer.get_printer_status()
    context = {'files': files, 'printer_status': printer_status}
    return render(request, 'index.html', context)


def upload_file(request):
    session_key = _ensure_session_key(request)
    app_settings = get_app_settings()
    if app_settings is not None:
        app_settings.refresh_from_db()

    printer_selected = (
        app_settings is not None
        and app_settings.printer_profile != DEFAULT_APP_SETTINGS['printer_profile']
    )
    form = FileUploadForm()

    if request.method == 'POST':
        upload = request.FILES.get('file_upload')
        if upload is None:
            messages.error(request, 'No file was selected for upload.')
            return redirect('index')

        ext = Path(upload.name).suffix.lower()
        if not ext or ext not in SUPPORTED_UPLOAD_EXTENSIONS:
            messages.error(request, 'File type not supported')
            return redirect('index')

        requires_conversion = ext not in CUPS_NATIVE_EXTENSIONS
        upload.name = _sanitize_upload_name(upload.name)

        # Get settings object to apply defaults to the new file object:
        default_color = DEFAULT_APP_SETTINGS['default_color']
        default_orientation = DEFAULT_APP_SETTINGS['default_orientation']

        if app_settings is not None:
            default_color = app_settings.default_color or default_color
            default_orientation = app_settings.default_orientation or default_orientation

        ensure_uploads_dir_exists()
        storage = FileSystemStorage(location=str(UPLOADS_DIR))

        try:
            saved_name = storage.save(upload.name, upload)
        except Exception:
            messages.error(request, 'An unexpected error occurred while saving the file. Please try again.')
            return redirect('index')

        final_name = saved_name
        if requires_conversion:
            pdf_candidate = Path(saved_name).with_suffix('.pdf').name
            pdf_name = storage.get_available_name(pdf_candidate)
            pdf_path = Path(storage.path(pdf_name))

            def _handle_conversion_failure(message: str):
                storage.delete(saved_name)
                try:
                    pdf_path.unlink(missing_ok=True)
                except OSError:
                    pass
                messages.error(request, message)
                return redirect('index')

            try:
                convert_document_to_pdf(Path(storage.path(saved_name)), pdf_path)
            except ConversionError as exc:
                return _handle_conversion_failure(
                    f'Unable to convert {saved_name} to PDF: {exc}'
                )
            except Exception:
                return _handle_conversion_failure(
                    'An unexpected error occurred while converting the file. Please try again.'
                )

            storage.delete(saved_name)
            final_name = pdf_name

        File.objects.create(
            name=final_name,
            page_range='0',
            pages='All',
            color=default_color,
            orientation=default_orientation,
            session_key=session_key,
        )
        if requires_conversion:
            messages.success(request, f'Converted and queued {final_name} for printing.')
        else:
            messages.success(request, f'Queued {final_name} for printing.')
        return redirect('index')

    context = {'printer_selected': printer_selected, 'form': form}
    return render(request, 'upload_file.html', context)


def edit_file(request, file_id):
    file_obj = _get_session_file(request, file_id)
    file_obj.refresh_from_db()
    context = {'file': file_obj}
    return render(request, 'edit_file.html', context)


@require_POST
def submit_edit_file_form(request):
    try:
        file_id = int(request.POST.get('file_id', ''))
    except (TypeError, ValueError):
        return HttpResponse(status=400)

    file_obj = _get_session_file(request, file_id)

    page_range = request.POST.get('page_range', '').strip()
    pages = request.POST.get('pages', '').strip()
    color = request.POST.get('color', '').strip()
    orientation = request.POST.get('orientation', '').strip()

    valid_page_ranges = {choice for choice, _ in PrintOptions.RANGE_OPTIONS}
    valid_colors = {choice for choice, _ in PrintOptions.COLOR_OPTIONS}
    valid_orientations = {choice for choice, _ in PrintOptions.ORIENTATION_OPTIONS}

    if (
        page_range not in valid_page_ranges
        or color not in valid_colors
        or orientation not in valid_orientations
    ):
        return HttpResponse(status=400)

    if page_range == '0':
        pages_value = 'All'
    else:
        pages_value = pages or '1-1'

    file_obj.page_range = page_range
    file_obj.pages = pages_value
    file_obj.color = color
    file_obj.orientation = orientation
    file_obj.save(update_fields=['page_range', 'pages', 'color', 'orientation'])
    return HttpResponse(status=200)


@require_POST
def delete_file(request, file_id):
    file_obj = _get_session_file(request, file_id)
    file_name = file_obj.name
    file_obj.delete()
    messages.success(request, f'Removed {file_name} from the queue.')

    return redirect('index')


@require_POST
def print_files(request):
    session_key = _ensure_session_key(request)
    _claim_legacy_files(session_key)

    files = list(
        File.objects.filter(session_key=session_key).order_by('uploaded_at')
    )
    if not files:
        messages.info(request, 'No files are queued for printing.')
        return HttpResponse(status=204)

    errors = False
    successful_jobs = 0

    for file_obj in files:
        try:
            _stdout, stderr = file_printer.print_file(
                file_obj.name,
                file_obj.page_range,
                file_obj.pages,
                file_obj.color,
                file_obj.orientation,
            )
        except Exception as exc:
            errors = True
            messages.error(request, f'Failed to print {file_obj.name}: {exc}')
            continue

        error_message = (stderr or b'').decode(errors='replace').strip()
        if error_message:
            errors = True
            messages.error(request, error_message)
            continue

        messages.info(request, f'Printing {file_obj.name}')
        file_obj.delete()
        successful_jobs += 1

    if errors:
        return HttpResponse(status=500)

    if successful_jobs:
        messages.success(request, 'Jobs completed')
    else:
        messages.info(request, 'No files were printed.')
    return HttpResponse(status=204)


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

        if form.is_valid():
            form.save()
            file_printer.refresh_printer_profile()
            return redirect('index')

        messages.error(request, 'Please correct the errors below.')

    context = {'settings': app_settings, 'form': form}
    return render(request, 'settings.html', context)
