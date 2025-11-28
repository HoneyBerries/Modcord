"""Image downloading and processing utilities for moderation."""

import asyncio
import hashlib
from io import BytesIO
import discord
from modcord.datatypes.moderation_datatypes import ModerationImage
from modcord.datatypes.image_datatypes import ImageURL, ImageID
import requests
from PIL import Image
from pillow_heif import register_heif_opener
from modcord.util.logger import get_logger

logger = get_logger("image_utils")

register_heif_opener()

def generate_image_hash_id(image_url: ImageURL) -> ImageID:
    """
    Generate a unique 8-character ImageID for an image based on its URL.
    
    Args:
        image_url: The URL of the image (as ImageURL type).
        
    Returns:
        ImageID: First 8 characters of SHA3-512 hash wrapped in ImageID.
    """
    hash_obj = hashlib.sha3_512(str(image_url).encode('utf-8'))
    return ImageID(hash_obj.hexdigest()[:8])


def download_image_to_pil(url: str) -> Image.Image | None:
    """
    Download an image from a URL and return it as a resized PIL Image in RGB mode.
    
    The image is automatically resized so that the longest side is 512 pixels while
    maintaining aspect ratio. This helps reduce memory usage and processing time. This function blocks the calling thread so it should be called asynchronously.
    
    Args:
        url (str): The URL of the image to download.
        timeout (int): Timeout for the HTTP request in seconds. Defaults to 2.
    
    Returns:
        Image.Image | None: The downloaded image as a PIL Image object in RGB mode,
            resized so the longest side is 512 pixels. Returns None if the download
            or conversion fails.
    
    Note:
        All exceptions are caught and logged internally to prevent crashes.
    """
    
    try:
        logger.debug(f"[DOWNLOAD] Downloading image from {url}")
        response = requests.get(url, timeout=2)
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




def is_image_attachment(attachment: discord.Attachment) -> bool:
    """
    Determine if a Discord attachment is an image.
    
    Checks multiple indicators to identify image attachments:
    1. Content type starts with "image/"
    2. Attachment has width and height properties
    3. Filename ends with common image extensions
    
    Args:
        attachment (discord.Attachment): The attachment to check.
    
    Returns:
        bool: True if the attachment is identified as an image, False otherwise.
    """
    content_type = (attachment.content_type or "").lower()
    if content_type.startswith("image/"):
        return True
    if attachment.width is not None and attachment.height is not None:
        return True
    filename = (attachment.filename or "").lower()
    return filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heif"))


async def download_images_for_moderation(message: discord.Message) -> list[ModerationImage]:
    """Download and process all image attachments from a Discord message.
    
    This function:
    1. Filters attachments to only include images
    2. Downloads each image asynchronously (in a thread to avoid blocking)
    3. Resizes images to max 512px on longest side
    4. Returns ModerationImage objects with loaded PIL images
    
    Args:
        message: The Discord message to extract images from.
        
    Returns:
        List of ModerationImage objects with pil_image populated.
        Only successfully downloaded images are included.
    """
    # Build list of (url, ModerationImage) for image attachments
    image_tuples: list[tuple[str, ModerationImage]] = []
    
    for attachment in message.attachments:
        if not is_image_attachment(attachment):
            continue
        
        image_url = ImageURL.from_url(attachment.url)
        image_id = generate_image_hash_id(attachment.url)
        
        mod_image = ModerationImage(
            image_id=image_id,
            image_url=image_url,
            pil_image=None,
        )
        image_tuples.append((attachment.url, mod_image))
    
    # Download images concurrently
    successful_images: list[ModerationImage] = []
    
    for url, img in image_tuples:
        # Run download in thread to avoid blocking event loop
        pil_image = await asyncio.to_thread(download_image_to_pil, url)
        if pil_image:
            img.pil_image = pil_image
            successful_images.append(img)
        else:
            logger.warning(f"Failed to download image from {url}")
    
    return successful_images