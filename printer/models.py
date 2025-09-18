from django.db import models

from pathlib import Path

from .paths import UPLOADS_DIR


class File(models.Model):
    uploaded_at = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=300)
    page_range = models.CharField(max_length=1, blank=True, null=True)
    pages = models.CharField(max_length=6)
    color = models.CharField(max_length=4)
    orientation = models.CharField(max_length=1)
    session_key = models.CharField(max_length=40, blank=True, default='', db_index=True)
    file_type = models.CharField(max_length=20)

    _FILE_TYPE_LABELS = {
        '.pdf': 'PDF',
        '.ps': 'PostScript',
        '.txt': 'Plain text',
        '.jpg': 'JPEG image',
        '.jpeg': 'JPEG image',
        '.png': 'PNG image',
        '.gif': 'GIF image',
        '.tif': 'TIFF image',
        '.tiff': 'TIFF image',
    }

    def determine_file_type(self, filename):
        suffix = Path(filename).suffix.lower()
        self.file_type = self._FILE_TYPE_LABELS.get(suffix, 'Unknown format')

    def save(self, *args, **kwargs):
        self.determine_file_type(self.name.lower())

        super(File, self).save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        try:
            (UPLOADS_DIR / self.name).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

        return super(File, self).delete(using=using, keep_parents=keep_parents)

    class Meta:
        verbose_name_plural = 'files'


class Settings(models.Model):
    app_title = models.CharField(max_length=32, blank=False, null=False)
    default_color = models.CharField(max_length=4, blank=False, null=False)
    default_orientation = models.CharField(max_length=1, blank=False, null=False)
    printer_profile = models.TextField()
