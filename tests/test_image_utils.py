"""Tests for image_utils module."""

import pytest
from unittest.mock import patch, Mock
from PIL import Image
import io
import requests

from modcord.util.image_utils import (
    generate_image_hash_id,
    download_image_to_pil,
)


class TestGenerateImageHashId:
    """Tests for generate_image_hash_id function."""

    def test_hash_generation(self):
        """Test that hash ID is generated correctly."""
        url = "https://example.com/image.jpg"
        hash_id = generate_image_hash_id(url)
        
        # Should return 8-character string
        assert isinstance(hash_id, str)
        assert len(hash_id) == 8

    def test_hash_consistency(self):
        """Test that same URL produces same hash."""
        url = "https://example.com/image.jpg"
        hash1 = generate_image_hash_id(url)
        hash2 = generate_image_hash_id(url)
        
        assert hash1 == hash2

    def test_different_urls_different_hashes(self):
        """Test that different URLs produce different hashes."""
        url1 = "https://example.com/image1.jpg"
        url2 = "https://example.com/image2.jpg"
        
        hash1 = generate_image_hash_id(url1)
        hash2 = generate_image_hash_id(url2)
        
        assert hash1 != hash2

    def test_hash_hex_characters(self):
        """Test that hash contains only hex characters."""
        url = "https://example.com/image.jpg"
        hash_id = generate_image_hash_id(url)
        
        # Should be valid hex string
        assert all(c in '0123456789abcdef' for c in hash_id)

    def test_empty_url(self):
        """Test hash generation with empty URL."""
        hash_id = generate_image_hash_id("")
        assert isinstance(hash_id, str)
        assert len(hash_id) == 8


class TestDownloadImageToPil:
    """Tests for download_image_to_pil function."""

    @patch('modcord.util.image_utils.requests.get')
    def test_successful_download(self, mock_get):
        """Test successful image download and conversion."""
        # Create a test image
        img = Image.new('RGB', (1000, 1000), color='blue')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)
        
        # Mock the response
        mock_response = Mock()
        mock_response.content = img_bytes.read()
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = download_image_to_pil("https://example.com/image.jpg")
        
        assert result is not None
        assert isinstance(result, Image.Image)
        assert result.mode == 'RGB'
        # Check that image was resized (longest side should be 512)
        assert max(result.size) == 512

    @patch('modcord.util.image_utils.requests.get')
    def test_download_resize_width_larger(self, mock_get):
        """Test image resizing when width is larger than height."""
        # Create wide image (800x400)
        img = Image.new('RGB', (800, 400), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)
        
        mock_response = Mock()
        mock_response.content = img_bytes.read()
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = download_image_to_pil("https://example.com/image.jpg")
        
        assert result is not None
        # Width should be 512, height proportionally smaller
        assert result.size[0] == 512
        assert result.size[1] == 256

    @patch('modcord.util.image_utils.requests.get')
    def test_download_resize_height_larger(self, mock_get):
        """Test image resizing when height is larger than width."""
        # Create tall image (300x900)
        img = Image.new('RGB', (300, 900), color='green')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)
        
        mock_response = Mock()
        mock_response.content = img_bytes.read()
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = download_image_to_pil("https://example.com/image.jpg")
        
        assert result is not None
        # Height should be 512, width proportionally smaller
        assert result.size[1] == 512
        assert result.size[0] == 170  # 300 * 512 / 900 = 170.67 -> 170

    @patch('modcord.util.image_utils.requests.get')
    def test_download_rgb_conversion(self, mock_get):
        """Test that images are converted to RGB mode."""
        # Create RGBA image
        img = Image.new('RGBA', (100, 100), color='yellow')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        mock_response = Mock()
        mock_response.content = img_bytes.read()
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = download_image_to_pil("https://example.com/image.png")
        
        assert result is not None
        assert result.mode == 'RGB'

    @patch('modcord.util.image_utils.requests.get')
    def test_download_timeout_parameter(self, mock_get):
        """Test that timeout parameter is used."""
        img = Image.new('RGB', (100, 100), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)
        
        mock_response = Mock()
        mock_response.content = img_bytes.read()
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        download_image_to_pil("https://example.com/image.jpg", timeout=5)
        
        mock_get.assert_called_once_with("https://example.com/image.jpg", timeout=5)

    @patch('modcord.util.image_utils.requests.get')
    def test_download_request_exception(self, mock_get):
        """Test handling of request exceptions."""
        mock_get.side_effect = requests.RequestException("Network error")
        
        result = download_image_to_pil("https://example.com/image.jpg")
        
        assert result is None

    @patch('modcord.util.image_utils.requests.get')
    def test_download_http_error(self, mock_get):
        """Test handling of HTTP errors."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_get.return_value = mock_response
        
        result = download_image_to_pil("https://example.com/image.jpg")
        
        assert result is None

    @patch('modcord.util.image_utils.requests.get')
    def test_download_invalid_image_data(self, mock_get):
        """Test handling of invalid image data."""
        mock_response = Mock()
        mock_response.content = b"not an image"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = download_image_to_pil("https://example.com/image.jpg")
        
        assert result is None

    @patch('modcord.util.image_utils.requests.get')
    def test_download_small_image_resized(self, mock_get):
        """Test that small images are resized to 512."""
        # Create small image (100x100)
        img = Image.new('RGB', (100, 100), color='purple')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)
        
        mock_response = Mock()
        mock_response.content = img_bytes.read()
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = download_image_to_pil("https://example.com/image.jpg")
        
        assert result is not None
        # Small images are upscaled to 512x512
        assert result.size == (512, 512)
