"""
ASGI config for printer project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

from .auto_migrate import ensure_migrations_applied

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'printer.settings')

application = get_asgi_application()
ensure_migrations_applied()
