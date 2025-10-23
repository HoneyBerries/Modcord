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
    Downloads an image from a given URL and returns it as a resized PIL Image in RGB mode.
        url (str): The URL of the image to download.
        timeout (int, optional): Timeout for the HTTP request in seconds. Defaults to 2.
        Optional[Image.Image]: The downloaded image as a PIL Image object in RGB mode, resized so the longest side is 512 pixels.
        Returns None if the download or conversion fails.
    Raises:
        None. All exceptions are caught and logged internally.
    """
    
    try:
        logger.debug(f"[DOWNLOAD] Downloading image from {url}")
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        
        img = Image.open(BytesIO(response.content)).convert("RGB")

        # Resize image for efficiency
        max_side = 512
        w, h = img.size

        if w > h:
            new_w = max_side
            new_h = int(h * max_side / w)
        else:
            new_h = max_side
            new_w = int(w * max_side / h)

        img = img.resize((new_w, new_h))
        logger.debug(f"[DOWNLOAD] Successfully downloaded image, resized={img.size}")
        return img
    except requests.RequestException as exc:
        logger.error(f"[DOWNLOAD] Request failed for {url}: {exc}")
        return None
    except Exception as exc:
        logger.error(f"[DOWNLOAD] Failed to process image from {url}: {exc}")
        return None
