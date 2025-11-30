import pytest
from modcord.util.discord.discord_utils import format_duration, parse_duration_to_minutes, extract_embed_text_from_message, is_ignored_author

class MockEmbed:
    def __init__(self, description=None, fields=None):
        self.description = description
        self.fields = fields or []

class MockField:
    def __init__(self, name, value):
        self.name = name
        self.value = value

class MockUser:
    def __init__(self, bot=False):
        self.bot = bot

class MockMember(MockUser):
    pass

@pytest.mark.parametrize("seconds,expected", [
    (0, "Till the End of Time"),
    (45, "45 secs"),
    (120, "2 mins"),
    (3600, "1 hour"),
    (7200, "2 hours"),
    (86400, "1 day"),
    (172800, "2 days"),
])
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected

@pytest.mark.parametrize("label,expected", [
    ("60 secs", 1),
    ("5 mins", 5),
    ("1 hour", 60),
    ("1 day", 1440),
    ("Till the End of Time", 0),
    ("unknown", 0),
])
def test_parse_duration_to_minutes(label, expected):
    assert parse_duration_to_minutes(label) == expected

def test_extract_embed_text_from_message():
    embed = MockEmbed(description="Test description", fields=[
        MockField("Field1", "Value1"),
        MockField("Field2", "Value2"),
        MockField("", "Value3"),
    ])
    texts = extract_embed_text_from_message(embed) # type: ignore
    assert "Test description" in texts
    assert "Field1: Value1" in texts
    assert "Field2: Value2" in texts
    assert "Value3" in texts

@pytest.mark.parametrize("author,expected", [
    (MockUser(bot=True), True),
    (MockUser(bot=False), True),  # Not a Member
    (MockMember(bot=False), False),
    (MockMember(bot=True), True),
])
def is_ignored_author(author):
    if isinstance(author, MockMember):
        return False
    return isinstance(author, MockUser) and author.bot