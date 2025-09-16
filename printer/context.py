from .utils import DEFAULT_APP_SETTINGS, get_app_settings


def add_to_context(request):
    app_settings = get_app_settings()
    if app_settings is None:
        return { 'app_title': DEFAULT_APP_SETTINGS['app_title'] }

    return { 'app_title': app_settings.app_title }
