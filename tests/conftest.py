"""Pytest configuration and fixtures for Modcord tests."""

import sys
from pathlib import Path
import pytest
import asyncio
from unittest.mock import Mock, MagicMock

# Add src directory to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture
def mock_discord_message():
    """Create a mock Discord message for testing."""
    message = MagicMock()
    message.id = 123456789
    message.content = "Test message content"
    message.author = MagicMock()
    message.author.id = 987654321
    message.author.display_name = "TestUser"
    message.author.bot = False
    message.guild = MagicMock()
    message.guild.id = 111222333
    message.guild.name = "Test Guild"
    message.channel = MagicMock()
    message.channel.id = 444555666
    message.channel.name = "test-channel"
    return message


@pytest.fixture
def mock_discord_member():
    """Create a mock Discord member for testing."""
    member = MagicMock()
    member.id = 987654321
    member.display_name = "TestUser"
    member.mention = "<@987654321>"
    member.bot = False
    member.guild_permissions = MagicMock()
    member.guild_permissions.administrator = False
    member.guild_permissions.manage_guild = False
    member.guild_permissions.moderate_members = False
    return member


@pytest.fixture
def mock_discord_user():
    """Create a mock Discord user for testing."""
    user = MagicMock()
    user.id = 987654321
    user.display_name = "TestUser"
    user.mention = "<@987654321>"
    user.bot = False
    return user


@pytest.fixture
def mock_discord_guild():
    """Create a mock Discord guild for testing."""
    guild = MagicMock()
    guild.id = 111222333
    guild.name = "Test Guild"
    guild.me = MagicMock()
    guild.text_channels = []
    return guild


@pytest.fixture
def mock_pil_image():
    """Create a mock PIL Image for testing."""
    from PIL import Image
    import io
    
    # Create a simple test image
    img = Image.new('RGB', (100, 100), color='red')
    return img


@pytest.fixture
async def temp_database():
    """Create a temporary database for testing."""
    import tempfile
    import os
    from modcord.database import database
    
    # Save original DB path
    original_path = database.DB_PATH
    
    # Create temporary database
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_file.close()
    database.DB_PATH = Path(temp_file.name)
    
    # Initialize database
    await database.init_database()
    
    yield database.DB_PATH
    
    # Cleanup
    database.DB_PATH = original_path
    try:
        os.unlink(temp_file.name)
    except:
        pass
