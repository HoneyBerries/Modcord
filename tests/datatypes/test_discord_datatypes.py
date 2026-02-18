import pytest

from modcord.datatypes.discord_datatypes import (
    UserID,
    DiscordUsername,
    GuildID,
    ChannelID,
    MessageID,
)


class DummyObj:
    def __init__(self, id_val=None, string_repr=None):
        self.id = id_val
        self._string = string_repr

    def __str__(self):
        return self._string or f"Dummy({self.id})"


def test_userid_from_int_and_str_and_equality_and_hash():
    u1 = UserID(12345)
    assert int(u1) == 12345
    assert str(u1) == "12345"

    u2 = UserID("12345")
    assert u1 == u2

    u3 = UserID.from_int(67890)
    assert isinstance(u3, UserID)
    assert int(u3) == 67890

    # from_user helper
    dummy = DummyObj(id_val=111)
    u4 = UserID.from_user(dummy) # type: ignore
    assert int(u4) == 111

    # equality with raw types
    assert u4 == 111
    assert u4 == "111"

    # hashing and set membership
    s = {u1, u2, u3, u4}
    assert len(s) == 3


def test_userid_invalid():
    with pytest.raises(ValueError):
        UserID([])  # type: ignore # unsupported type


def test_discordusername_behavior_and_defaults():
    d1 = DiscordUsername("Alice#0001")
    assert str(d1) == "Alice#0001"

    d2 = DiscordUsername(DiscordUsername("Bob"))
    assert str(d2) == "Bob"

    d_empty = DiscordUsername("")
    assert str(d_empty) != ""  # falls back to default unknown token

    unknown = DiscordUsername.unknown()
    assert str(unknown) == DiscordUsername.DEFAULT_USERNAME

    # from_user uses str(member)
    dummy = DummyObj(id_val=1, string_repr="SomeUser#1234")
    from_user = DiscordUsername.from_user(dummy) # type: ignore
    assert str(from_user) == "SomeUser#1234"


@pytest.mark.parametrize("cls, val_int", [(GuildID, 222), (ChannelID, 333), (MessageID, 444)])
def test_id_wrappers_common_behaviour(cls, val_int):
    inst = cls(val_int)
    assert int(inst) == val_int
    assert str(inst) == str(val_int)

    inst2 = cls(str(val_int))
    assert inst == inst2

    # from_* helpers
    dummy = DummyObj(id_val=val_int)
    if cls is GuildID:
        inst3 = cls.from_guild(dummy) # type: ignore
    elif cls is ChannelID:
        inst3 = cls.from_channel(dummy) # type: ignore
    else:
        inst3 = cls.from_message(dummy)
    assert int(inst3) == val_int

    # equality with raw types
    assert inst == val_int
    assert inst == str(val_int)


@pytest.mark.parametrize("cls", [GuildID, ChannelID, MessageID])
def test_id_wrappers_invalid_input_raise(cls):
    with pytest.raises(ValueError):
        cls({"not": "valid"})
