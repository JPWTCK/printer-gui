from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from printer.models import File


class SessionIsolationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._temp_dir = Path(tempfile.mkdtemp())
        cls._patchers = [
            patch('printer.paths.UPLOADS_DIR', cls._temp_dir),
            patch('printer.views.UPLOADS_DIR', cls._temp_dir),
            patch('printer.models.UPLOADS_DIR', cls._temp_dir),
        ]
        for patcher in cls._patchers:
            patcher.start()
            cls.addClassCleanup(patcher.stop)

        cls.addClassCleanup(lambda: shutil.rmtree(cls._temp_dir, ignore_errors=True))

    def _upload_sample_file(self, client: Client) -> None:
        upload = SimpleUploadedFile(
            'example.pdf', b'%PDF-1.4', content_type='application/pdf'
        )
        response = client.post(reverse('upload_file'), {'file_upload': upload})
        self.assertEqual(response.status_code, 302)

    def test_upload_assigns_session_key(self) -> None:
        self._upload_sample_file(self.client)

        self.assertIsNotNone(self.client.session.session_key)

        stored_file = File.objects.get()
        self.assertEqual(stored_file.session_key, self.client.session.session_key)

    def test_sessions_are_isolated(self) -> None:
        self._upload_sample_file(self.client)
        stored_file = File.objects.get()

        other_client = Client()
        response = other_client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['files']), [])

        with patch('printer.views.file_printer.print_file', return_value=(b'', b'')):
            response = other_client.post(reverse('print_files'))
        self.assertEqual(response.status_code, 204)
        self.assertTrue(File.objects.filter(id=stored_file.id).exists())

        with patch('printer.views.file_printer.print_file', return_value=(b'', b'')):
            response = self.client.post(reverse('print_files'))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(File.objects.filter(id=stored_file.id).exists())

    def test_cross_session_file_actions_return_404(self) -> None:
        self._upload_sample_file(self.client)
        stored_file = File.objects.get()

        other_client = Client()
        response = other_client.post(reverse('delete_file', args=[stored_file.id]))
        self.assertEqual(response.status_code, 404)

        response = other_client.post(
            reverse('submit_edit_file_form'),
            data={
                'file_id': stored_file.id,
                'page_range': '0',
                'pages': 'All',
                'color': 'RGB',
                'orientation': '3',
            },
        )
        self.assertEqual(response.status_code, 404)
