"""Top-level package for the Modcord project.

This file provides minimal package metadata (a best-effort __version__) and
a tiny helper to retrieve that version. Importlib.metadata is used when the
package is installed; when running from a source tree the version falls back
to a placeholder.
"""
from __future__ import annotations

from importlib import metadata as importlib_metadata


try:
    __version__ = importlib_metadata.version("modcord")
except Exception:  # pragma: no cover - fallback when not installed
    __version__ = "0.0.0"


def get_version() -> str:
    """Return the package version string.

    This helper prefers the installed distribution metadata but will return
    the fallback version when running from source.
    """
    return __version__


__all__ = ["get_version", "__version__"]
