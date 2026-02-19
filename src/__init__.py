"""Top-level package for the Modcord project.

This file provides minimal package metadata (a best-effort __version__) and
a tiny helper to retrieve that version. Importlib.metadata is used when the
package is installed; when running from a source tree the version falls back
to a placeholder.
"""
from __future__ import annotations

from importlib import metadata as importlib_metadata
__version__ = importlib_metadata.version("modcord")