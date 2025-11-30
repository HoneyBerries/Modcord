from PIL import Image
from modcord.util.image_utils import download_image_to_pil, generate_image_hash_id
from modcord.datatypes.image_datatypes import ImageURL

IMAGE_URLS_RAW = [
    "https://honeyberries.net/assets/backgrounds/home-banner.webp",
    "https://honeyberries.net/assets/backgrounds/minecraft-plugin-background.webp",
    "https://honeyberries.net/assets/backgrounds/minecraft-server-background.webp",
    "https://honeyberries.net/assets/backgrounds/modcord-background.webp",
]

IMAGE_URLS = [ImageURL(url) for url in IMAGE_URLS_RAW]

def test_download_image_to_pil_valid_urls():
    for url in IMAGE_URLS:
        img = download_image_to_pil(str(url))
        assert img is not None, f"Image should be downloaded for {url}"
        assert isinstance(img, Image.Image)
        assert img.mode == "RGB"
        w, h = img.size
        assert max(w, h) == 512, f"Longest side should be 512 for {url}"

def test_generate_image_hash_id_unique():
    hashes = set()
    for url in IMAGE_URLS:
        image_id = generate_image_hash_id(ImageURL(url))
        assert isinstance(image_id, str) or hasattr(image_id, "__str__")
        hashes.add(str(image_id))
    assert len(hashes) == len(IMAGE_URLS), "Each URL should produce a unique hash"