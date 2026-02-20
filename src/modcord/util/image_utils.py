"""Image processing utilities for moderation."""

import discord
from modcord.datatypes.image_datatypes import ImageLink, ImageID
from modcord.datatypes.moderation_datatypes import ModerationImage


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


def extract_images_for_moderation(message: discord.Message) -> list[ModerationImage]:
    """Extract image information from a Discord message.
    
    This function:
    1. Filters attachments to only include images
    2. Creates ModerationImage objects with URLs and hash IDs
    
    Args:
        message: The Discord message to extract images from.
        
    Returns:
        List of ModerationImage objects with image_url and image_id populated.
    """
    images: list[ModerationImage] = []
    
    for attachment in message.attachments:
        if not is_image_attachment(attachment):
            continue
        
        image_url = ImageLink.from_url(attachment.url)
        image_id = ImageID.from_url(image_url)
        
        images.append(ModerationImage(
            image_id=image_id,
            image_url=image_url,
        ))
    
    return images