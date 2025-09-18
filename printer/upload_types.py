"""Supported upload formats and helpers for printer-gui."""

from __future__ import annotations

from typing import Dict, List, Set

# File extensions CUPS can render without an intermediate conversion step.
CUPS_NATIVE_EXTENSIONS: Set[str] = {
    ".pdf",
    ".ps",
    ".txt",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".tif",
    ".tiff",
}

# Formats that require Docuvert to render an intermediate PDF before printing.
DOCUVERT_CONVERTIBLE_EXTENSIONS: Set[str] = {
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".odt",
    ".odp",
    ".ods",
    ".rtf",
}

SUPPORTED_UPLOAD_EXTENSIONS: Set[str] = (
    CUPS_NATIVE_EXTENSIONS | DOCUVERT_CONVERTIBLE_EXTENSIONS
)

# Display labels and MIME type hints for each supported extension. The order in
# ``_DISPLAY_ORDER`` prioritizes the long-standing CUPS-native formats followed
# by the Docuvert-powered conversions so related file types appear together in
# the UI.
_EXTENSION_DISPLAY_LABELS: Dict[str, str] = {
    ".pdf": "pdf",
    ".ps": "ps",
    ".txt": "txt",
    ".jpg": "jpg",
    ".jpeg": "jpeg",
    ".png": "png",
    ".gif": "gif",
    ".tif": "tif",
    ".tiff": "tiff",
    ".doc": "doc",
    ".docx": "docx",
    ".ppt": "ppt",
    ".pptx": "pptx",
    ".xls": "xls",
    ".xlsx": "xlsx",
    ".odt": "odt",
    ".odp": "odp",
    ".ods": "ods",
    ".rtf": "rtf",
}

_EXTENSION_MIME_TYPES: Dict[str, str] = {
    ".pdf": "application/pdf",
    ".ps": "application/postscript",
    ".txt": "text/plain",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".rtf": "application/rtf",
}

_DISPLAY_ORDER: List[str] = [
    ".pdf",
    ".ps",
    ".txt",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".tif",
    ".tiff",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".odt",
    ".odp",
    ".ods",
    ".rtf",
]


def describe_supported_extensions() -> str:
    """Return a human-readable summary of supported upload extensions."""

    labels: List[str] = []
    added = set()
    for extension in _DISPLAY_ORDER:
        if extension not in SUPPORTED_UPLOAD_EXTENSIONS or extension in added:
            continue
        labels.append(_EXTENSION_DISPLAY_LABELS.get(extension, extension.lstrip(".")))
        added.add(extension)

    for extension in sorted(SUPPORTED_UPLOAD_EXTENSIONS - added):
        labels.append(_EXTENSION_DISPLAY_LABELS.get(extension, extension.lstrip(".")))

    return ", ".join(labels)


def build_accept_attribute() -> str:
    """Return a comma-separated list of MIME types for ``<input accept=...>``."""

    accept_types = {
        mime_type
        for ext, mime_type in _EXTENSION_MIME_TYPES.items()
        if ext in SUPPORTED_UPLOAD_EXTENSIONS
    }
    return ",".join(sorted(accept_types))
