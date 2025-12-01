import pytest
from modcord.util.discord.collector import is_rules_channel, collect_channel_topic

class MockChannel:
    def __init__(self, name, topic=None):
        self.name = name
        self.topic = topic

@pytest.mark.parametrize("name,expected", [
    ("rules", True),
    ("server-rules", True),
    ("guidelines", True),
    ("moderation-only-rules", False),
    ("general", False),
    ("code-of-conduct", True),
    ("mod-guidelines", True),
    ("random", False),
    ("law", True),
    ("expectations", True),
    ("moderationonly", False),
])
def test_is_rules_channel(name, expected):
    ch = MockChannel(name)
    assert is_rules_channel(ch) == expected # type: ignore

def test_collect_channel_topic():
    ch_with_topic = MockChannel("general", topic="Be nice to everyone!")
    ch_empty_topic = MockChannel("general", topic="   ")
    ch_no_topic = MockChannel("general")
    assert collect_channel_topic(ch_with_topic) == "Be nice to everyone!" # type: ignore
    assert collect_channel_topic(ch_empty_topic) == "" # type: ignore
    assert collect_channel_topic(ch_no_topic) == "" # type: ignore