from django.db import models
from . import settings

import os


UPLOADS_DIR = settings.STATICFILES_DIRS[0] + '/uploads/'


class File(models.Model):
    uploaded_at = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=300)
    page_range = models.CharField(max_length=1, blank=True, null=True)
    pages = models.CharField(max_length=6)
    color = models.CharField(max_length=4)
    orientation = models.CharField(max_length=1)
    file_type = models.CharField(max_length=20)

    def determine_file_type(self, filename):
        if filename.endswith('pdf'):
            self.file_type = 'PDF'
        elif filename.endswith('ps'):
            self.file_type = 'PostScript'
        elif filename.endswith('txt'):
            self.file_type = 'Plain text'
        elif filename.endswith('jpg') or filename.endswith('jpeg'):
            self.file_type = 'JPEG image'
        elif filename.endswith('png'):
            self.file_type = 'PNG image'
        elif filename.endswith('gif'):
            self.file_type = 'GIF image'
        elif filename.endswith('tif') or filename.endswith('tiff'):
            self.file_type = 'TIFF image'
        else:
            self.file_type = 'Unknown format'

    def save(self, *args, **kwargs):
        self.determine_file_type(self.name.lower())

        super(File, self).save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        try:
            os.remove(f"{UPLOADS_DIR}{self.name}")
        except FileNotFoundError:
            pass

        return super(File, self).delete(using=using, keep_parents=keep_parents)

    class Meta:
        verbose_name_plural = 'files'


class Settings(models.Model):
    app_title = models.CharField(max_length=32, blank=False, null=False)
    default_color = models.CharField(max_length=4, blank=False, null=False)
    default_orientation = models.CharField(max_length=1, blank=False, null=False)
    printer_profile = models.TextField()
