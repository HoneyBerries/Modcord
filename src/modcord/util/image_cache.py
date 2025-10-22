"""Helpers for downloading and converting images to PIL format for model consumption."""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urlsplit
import urllib.request

from PIL import Image

from modcord.util.logger import get_logger

logger = get_logger("image_cache")

CACHE_DIR = Path("data") / "image_cache"
_DOWNLOAD_TIMEOUT = 15
_MAX_BYTES = 20 * 1024 * 1024  # 20MB safety cap


def _guess_extension(url: str, fallback: str = ".bin") -> str:
    """Guess file extension from URL path, or return fallback."""
    path = urlsplit(url).path
    suffix = Path(path).suffix
    if suffix:
        return suffix[:16]
    return fallback


def _make_cache_path(extension: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(8)
    return CACHE_DIR / f"modcord_{token}{extension}"


def _stream_download(url: str, target: Path) -> Path:
    """Download image from URL to target path."""
    with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT) as response:
        total = 0
        with target.open("wb") as file_handle:
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_BYTES:
                    raise ValueError("image exceeds max download size")
                file_handle.write(chunk)
    return target


async def download_image_to_pil(url: str, *, suggested_name: str | None = None) -> Image.Image | None:
    """Download an image from URL and return as PIL Image object.
    
    Downloads to temporary cache file, converts to PIL Image, then deletes the temp file.
    Returns ``None`` on failure.
    """
    if not url:
        return None

    extension = Path(suggested_name or "").suffix or _guess_extension(url)
    target_path = _make_cache_path(extension)

    try:
        await asyncio.to_thread(_stream_download, url, target_path)
        # Load image into memory
        pil_image = Image.open(target_path)
        # Ensure image is loaded into memory before deleting the file
        pil_image.load()
        return pil_image
    except Exception as exc:
        logger.warning("Failed to download/convert image %s: %s", url, exc)
        return None
    finally:
        # Clean up temp file
        try:
            target_path.unlink(missing_ok=True)
        except OSError:
            pass


async def download_image(url: str, *, suggested_name: str | None = None) -> Path | None:
    """Download an image to the cache directory and return its path.

    Returns ``None`` on failure.
    """

    if not url:
        return None

    extension = Path(suggested_name or "").suffix or _guess_extension(url)
    target_path = _make_cache_path(extension)

    try:
        return await asyncio.to_thread(_stream_download, url, target_path)
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("Failed to download image %s: %s", url, exc)
        try:
            target_path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


async def cleanup_files(paths: Sequence[Path]) -> None:
    if not paths:
        return

    async def _remove_batch(files: Sequence[Path]) -> None:
        for file_path in files:
            try:
                file_path.unlink(missing_ok=True)
            except OSError:
                logger.debug("Failed to remove cached image %s", file_path)

    await asyncio.to_thread(_remove_batch, tuple(paths))


def iter_message_images(messages: Iterable[dict]) -> Iterable[dict]:
    for message in messages:
        for image in message.get("images", []) or []:
            yield image
