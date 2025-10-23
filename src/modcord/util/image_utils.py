"""Image downloading and processing utilities for moderation."""

import hashlib
from io import BytesIO
from typing import Optional

import requests
from PIL import Image

from modcord.util.logger import get_logger

logger = get_logger("image_utils")


def generate_image_hash_id(image_url: str) -> str:
    """
    Generate a unique 8-character hash ID for an image based on its URL.
    
    Args:
        image_url: The URL of the image
        
    Returns:
        First 8 characters of SHA3-512 hash
    """
    hash_obj = hashlib.sha3_512(image_url.encode('utf-8'))
    return hash_obj.hexdigest()[:8]


def download_image_to_pil(url: str, timeout: int = 2) -> Optional[Image.Image]:
    """
    Download an image from a URL and convert it to a PIL Image (RGB mode).
    
    Args:
        url: The URL of the image to download
        timeout: Request timeout in seconds
        
    Returns:
        PIL Image object in RGB mode, or None if download/conversion fails
    """
    try:
        logger.debug(f"[DOWNLOAD] Downloading image from {url}")
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        
        img = Image.open(BytesIO(response.content)).convert("RGB")
        logger.debug(f"[DOWNLOAD] Successfully downloaded image, size={img.size}")
        return img
    except requests.RequestException as exc:
        logger.error(f"[DOWNLOAD] Request failed for {url}: {exc}")
        return None
    except Exception as exc:
        logger.error(f"[DOWNLOAD] Failed to process image from {url}: {exc}")
        return None
