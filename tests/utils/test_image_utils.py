from modcord.util.image_utils import generate_image_hash_id
from modcord.datatypes.image_datatypes import ImageLink

IMAGE_URLS_RAW = [
    "https://honeyberries.net/assets/backgrounds/home-banner.webp",
    "https://honeyberries.net/assets/backgrounds/minecraft-plugin-background.webp",
    "https://honeyberries.net/assets/backgrounds/minecraft-server-background.webp",
    "https://honeyberries.net/assets/backgrounds/modcord-background.webp",
]

IMAGE_URLS = [ImageLink(url) for url in IMAGE_URLS_RAW]

def test_generate_image_hash_id_unique():
    hashes = set()
    for url in IMAGE_URLS:
        image_id = generate_image_hash_id(ImageLink(url))
        assert isinstance(image_id, str) or hasattr(image_id, "__str__")
        hashes.add(str(image_id))
    assert len(hashes) == len(IMAGE_URLS), "Each URL should produce a unique hash"