from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from printer.models import File
from printer.conversion import ConversionError


class FileConversionTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
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

    def setUp(self) -> None:
        super().setUp()
        for entry in self._temp_dir.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)

    def test_docx_file_is_converted(self) -> None:
        with patch('printer.views.convert_document_to_pdf') as convert_mock:
            def _write_pdf(source: Path, target: Path) -> None:
                target.write_bytes(b'%PDF-1.4')

            convert_mock.side_effect = _write_pdf
            response = self.client.post(
                reverse('upload_file'),
                {
                    'file_upload': SimpleUploadedFile(
                        'example.docx',
                        b'fake-docx',
                        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    )
                },
            )

        self.assertEqual(response.status_code, 302)
        stored_file = File.objects.get()
        self.assertTrue(stored_file.name.endswith('.pdf'))
        self.assertTrue((self._temp_dir / stored_file.name).exists())
        self.assertFalse(list(self._temp_dir.glob('*.docx')))

        convert_mock.assert_called_once()
        source_arg, target_arg = convert_mock.call_args[0]
        self.assertTrue(source_arg.name.endswith('.docx'))
        self.assertTrue(target_arg.name.endswith('.pdf'))

    def test_failed_conversion_reports_error(self) -> None:
        with patch('printer.views.convert_document_to_pdf', side_effect=ConversionError('boom')):
            response = self.client.post(
                reverse('upload_file'),
                {
                    'file_upload': SimpleUploadedFile(
                        'example.docx',
                        b'fake-docx',
                        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    )
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(File.objects.exists())
        self.assertFalse(list(self._temp_dir.iterdir()))

    def test_unsupported_extension_is_rejected(self) -> None:
        response = self.client.post(
            reverse('upload_file'),
            {
                'file_upload': SimpleUploadedFile(
                    'example.exe',
                    b'fake',
                    content_type='application/octet-stream',
                )
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(File.objects.exists())
        self.assertFalse(list(self._temp_dir.iterdir()))
