"""Utilities that convert uploaded files to PDF using Docuvert."""

from __future__ import annotations

import importlib
import shutil
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence


class ConversionError(RuntimeError):
    """Raised when Docuvert cannot render an upload to PDF."""


_DOCUVERT_CALLABLE: Optional[Callable[..., Any]] = None

# Candidate callable names and keyword parameters supported by Docuvert. The
# exact API differs across releases, so we probe common variations before
# giving up.
_CALLABLE_NAMES: Sequence[str] = (
    "convert_to_pdf",
    "convert_document",
    "convert",
    "convert_file",
)
_KEYWORD_VARIATIONS: Sequence[dict[str, Any]] = (
    {},
    {"output": None},
    {"output_path": None},
    {"target": None},
    {"destination": None},
    {"fmt": "pdf"},
    {"format": "pdf"},
)


def _load_docuvert_callable() -> Callable[..., Any]:
    try:
        module = importlib.import_module("docuvert")
    except ImportError as exc:  # pragma: no cover - exercised in production
        raise ConversionError(
            "Docuvert is not installed. Install docuvert==1.1.2 to enable "
            "format conversion."
        ) from exc

    for attr in _CALLABLE_NAMES:
        candidate = getattr(module, attr, None)
        if callable(candidate):
            return candidate

    for attr in ("Docuvert", "Docuverter", "Client", "Converter"):
        cls = getattr(module, attr, None)
        if cls is None:
            continue
        try:
            instance = cls()
        except Exception as exc:  # pragma: no cover - depends on Docuvert API
            raise ConversionError("Docuvert converter could not be instantiated.") from exc

        for name in _CALLABLE_NAMES:
            candidate = getattr(instance, name, None)
            if callable(candidate):
                return candidate

    raise ConversionError(
        "Docuvert 1.1.2 is available but does not expose a supported conversion "
        "function."
    )


def _get_docuvert_callable() -> Callable[..., Any]:
    global _DOCUVERT_CALLABLE

    if _DOCUVERT_CALLABLE is None:
        _DOCUVERT_CALLABLE = _load_docuvert_callable()
    return _DOCUVERT_CALLABLE


def _invoke_converter(
    converter: Callable[..., Any], source: Path, target: Path
) -> Any:
    args = (str(source), str(target))
    # Try a few call signatures so the integration tolerates minor API changes.
    for kwargs in _KEYWORD_VARIATIONS:
        prepared_kwargs = {}
        for key, value in kwargs.items():
            prepared_kwargs[key] = str(target) if value is None else value
        try:
            return converter(*args, **prepared_kwargs)
        except TypeError:
            continue
    raise ConversionError(
        "Docuvert conversion callable has an unsupported signature."
    )


def _normalize_result(result: Any, target: Path) -> None:
    if isinstance(result, (bytes, bytearray)):
        target.write_bytes(result)
        return

    candidate_paths: Iterable[Optional[Path]] = ()
    if isinstance(result, (str, Path)):
        candidate_paths = (Path(result),)
    elif isinstance(result, dict):
        candidate_paths = (
            Path(value)
            for key in ("output", "output_path", "path", "file", "file_path")
            if (value := result.get(key))
        )
    elif isinstance(result, (list, tuple)) and result:
        candidate_paths = (
            Path(value)
            for value in result
            if isinstance(value, (str, Path))
        )

    for candidate in candidate_paths:
        if candidate is None:
            continue
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError:
            continue
        if resolved == target.resolve():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(resolved), str(target))
        return

    # If Docuvert wrote directly to the target path the above logic is a no-op.
    if target.exists():
        return

    raise ConversionError("Docuvert did not produce a PDF output file.")


def convert_document_to_pdf(source: Path, target: Path) -> None:
    """Render ``source`` to ``target`` using Docuvert."""

    if source == target:
        raise ConversionError("Source and target paths must differ.")

    target.parent.mkdir(parents=True, exist_ok=True)
    converter = _get_docuvert_callable()
    try:
        result = _invoke_converter(converter, source, target)
    except ConversionError:
        raise
    except Exception as exc:  # pragma: no cover - depends on Docuvert's errors
        raise ConversionError(f"Docuvert failed to convert the file: {exc}") from exc

    _normalize_result(result, target)

    if not target.exists():
        raise ConversionError("Docuvert did not create the PDF output file.")
