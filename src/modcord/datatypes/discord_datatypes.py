"""
Type-safe wrapper classes for Discord identifiers.

This module provides type-safe wrappers for Discord snowflake IDs and usernames,
ensuring consistent handling throughout the moderation system.
"""

from __future__ import annotations

from typing import Union
import discord


class UserID:
    """
    Type-safe wrapper for Discord user snowflake IDs.
    
    Discord snowflakes are 64-bit integers, but are often stored/transmitted as strings
    for JSON compatibility. This class provides a consistent interface for working with
    user IDs throughout the moderation system.
    
    Attributes:
        _value (str): The snowflake ID stored as a string for JSON parity.
    
    Example:
        >>> uid = UserID.from_int(123456789012345678)
        >>> uid.to_int()
        123456789012345678
        >>> str(uid)
        '123456789012345678'
        >>> uid = UserID("123456789012345678")
        >>> uid.to_int()
        123456789012345678
    """
    
    __slots__ = ("_value",)
    
    def __init__(self, value: Union[str, int, "UserID"]) -> None:
        """
        Initialize a UserID from a string, int, or another UserID.
        
        Args:
            value: The snowflake ID as a string, int, or UserID.
        
        Raises:
            ValueError: If the value cannot be converted to a valid snowflake.
        """
        if isinstance(value, UserID):
            self._value = value._value
        elif isinstance(value, int):
            self._value = str(value)
        elif isinstance(value, str):
            # Validate that it's a valid integer string
            self._value = str(int(value.strip()))
        else:
            raise ValueError(f"Cannot create UserID from {type(value).__name__}: {value}")
    
    @classmethod
    def from_int(cls, value: int) -> "UserID":
        """
        Create a UserID from an integer snowflake.
        
        Args:
            value: The snowflake ID as an integer.
        
        Returns:
            UserID: A new UserID instance.
        """
        return cls(value)
    
    @classmethod
    def from_user(cls, member: Union[discord.Member, discord.User]) -> "UserID":
        """
        Create a UserID from a Discord Member or User object.
        
        Args:
            member: The Discord Member or User to extract the ID from.
        
        Returns:
            UserID: A new UserID instance.
        """
        return cls(member.id)
    
    def to_int(self) -> int:
        """
        Convert to an integer for Discord API calls.
        
        Returns:
            int: The snowflake ID as an integer.
        """
        return int(self._value)
    
    def __str__(self) -> str:
        """Return the string representation for JSON serialization."""
        return self._value
    
    def __repr__(self) -> str:
        return f"UserID({self._value!r})"
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, UserID):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other
        if isinstance(other, int):
            return self._value == str(other)
        return NotImplemented
    
    def __hash__(self) -> int:
        return hash(self._value)


class DiscordUsername:
    """
    Type-safe wrapper for Discord usernames.
    
    Discord usernames can include discriminators (e.g., "User#1234") or be
    the new-style usernames without discriminators. This class provides
    a consistent interface for working with usernames.
    
    Attributes:
        _value (str): The username string.
    
    Example:
        >>> username = DiscordUsername("TestUser#1234")
        >>> str(username)
        'TestUser#1234'
        >>> username = DiscordUsername.from_user(member)
    """
    
    __slots__ = ("_value",)
    
    DEFAULT_USERNAME = "<!@#$%^&*()_+>Unknown User"
    
    def __init__(self, value: Union[str, "DiscordUsername"]) -> None:
        """
        Initialize a DiscordUsername from a string or another DiscordUsername.
        
        Args:
            value: The username as a string or DiscordUsername.
        """
        if isinstance(value, DiscordUsername):
            self._value = value._value
        elif isinstance(value, str):
            self._value = value.strip() or self.DEFAULT_USERNAME
        else:
            self._value = self.DEFAULT_USERNAME
    
    @classmethod
    def from_user(cls, member: Union[discord.Member, discord.User]) -> "DiscordUsername":
        """
        Create a DiscordUsername from a Discord Member or User object.
        
        Args:
            member: The Discord Member or User to extract the username from.
        
        Returns:
            DiscordUsername: A new DiscordUsername instance.
        """
        return cls(str(member))
    
    @classmethod
    def unknown(cls) -> "DiscordUsername":
        """
        Create a DiscordUsername representing an unknown user.
        
        Returns:
            DiscordUsername: A new DiscordUsername with the default unknown value.
        """
        return cls(cls.DEFAULT_USERNAME)
    
    def __str__(self) -> str:
        """Return the string representation."""
        return self._value
    
    def __repr__(self) -> str:
        return f"DiscordUsername({self._value!r})"
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, DiscordUsername):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other
        return NotImplemented
    
    def __hash__(self) -> int:
        return hash(self._value)


class GuildID:
    """
    Type-safe wrapper for Discord guild snowflake IDs.
    
    Discord snowflakes are 64-bit integers, but are often stored/transmitted as strings
    for JSON compatibility. This class provides a consistent interface for working with
    guild IDs throughout the moderation system.
    
    Attributes:
        _value (str): The snowflake ID stored as a string for JSON parity.
    
    Example:
        >>> gid = GuildID.from_int(123456789012345678)
        >>> gid.to_int()
        123456789012345678
        >>> str(gid)
        '123456789012345678'
        >>> gid = GuildID("123456789012345678")
        >>> gid.to_int()
        123456789012345678
    """
    
    __slots__ = ("_value",)
    
    def __init__(self, value: Union[str, int, "GuildID"]) -> None:
        """
        Initialize a GuildID from a string, int, or another GuildID.
        
        Args:
            value: The snowflake ID as a string, int, or GuildID.
        
        Raises:
            ValueError: If the value cannot be converted to a valid snowflake.
        """
        if isinstance(value, GuildID):
            self._value = value._value
        elif isinstance(value, int):
            self._value = str(value)
        elif isinstance(value, str):
            # Validate that it's a valid integer string
            self._value = str(int(value.strip()))
        else:
            raise ValueError(f"Cannot create GuildID from {type(value).__name__}: {value}")
    
    @classmethod
    def from_int(cls, value: int) -> "GuildID":
        """
        Create a GuildID from an integer snowflake.
        
        Args:
            value: The snowflake ID as an integer.
        
        Returns:
            GuildID: A new GuildID instance.
        """
        return cls(value)
    
    @classmethod
    def from_guild(cls, guild: discord.Guild) -> "GuildID":
        """
        Create a GuildID from a Discord Guild object.
        
        Args:
            guild: The Discord Guild to extract the ID from.
        
        Returns:
            GuildID: A new GuildID instance.
        """
        return cls(guild.id)
    
    def to_int(self) -> int:
        """
        Convert to an integer for Discord API calls.
        
        Returns:
            int: The snowflake ID as an integer.
        """
        return int(self._value)
    
    def __str__(self) -> str:
        """Return the string representation for JSON serialization."""
        return self._value
    
    def __repr__(self) -> str:
        return f"GuildID({self._value!r})"
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, GuildID):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other
        if isinstance(other, int):
            return self._value == str(other)
        return NotImplemented
    
    def __hash__(self) -> int:
        return hash(self._value)


class ChannelID:
    """
    Type-safe wrapper for Discord channel snowflake IDs.
    
    Discord snowflakes are 64-bit integers, but are often stored/transmitted as strings
    for JSON compatibility. This class provides a consistent interface for working with
    channel IDs throughout the moderation system.
    
    Attributes:
        _value (str): The snowflake ID stored as a string for JSON parity.
    
    Example:
        >>> cid = ChannelID.from_int(123456789012345678)
        >>> cid.to_int()
        123456789012345678
        >>> str(cid)
        '123456789012345678'
        >>> cid = ChannelID("123456789012345678")
        >>> cid.to_int()
        123456789012345678
    """
    
    __slots__ = ("_value",)
    
    def __init__(self, value: Union[str, int, "ChannelID"]) -> None:
        """
        Initialize a ChannelID from a string, int, or another ChannelID.
        
        Args:
            value: The snowflake ID as a string, int, or ChannelID.
        
        Raises:
            ValueError: If the value cannot be converted to a valid snowflake.
        """
        if isinstance(value, ChannelID):
            self._value = value._value
        elif isinstance(value, int):
            self._value = str(value)
        elif isinstance(value, str):
            # Validate that it's a valid integer string
            self._value = str(int(value.strip()))
        else:
            raise ValueError(f"Cannot create ChannelID from {type(value).__name__}: {value}")
    
    @classmethod
    def from_int(cls, value: int) -> "ChannelID":
        """
        Create a ChannelID from an integer snowflake.
        
        Args:
            value: The snowflake ID as an integer.
        
        Returns:
            ChannelID: A new ChannelID instance.
        """
        return cls(value)
    
    @classmethod
    def from_channel(cls, channel: Union[discord.TextChannel, discord.Thread, discord.abc.GuildChannel, discord.abc.MessageableChannel]) -> "ChannelID":
        """
        Create a ChannelID from a Discord Channel object.
        
        Args:
            channel: The Discord Channel to extract the ID from.
        
        Returns:
            ChannelID: A new ChannelID instance.
        """
        return cls(channel.id)
    
    def to_int(self) -> int:
        """
        Convert to an integer for Discord API calls.
        
        Returns:
            int: The snowflake ID as an integer.
        """
        return int(self._value)
    
    def __str__(self) -> str:
        """Return the string representation for JSON serialization."""
        return self._value
    
    def __repr__(self) -> str:
        return f"ChannelID({self._value!r})"
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, ChannelID):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other
        if isinstance(other, int):
            return self._value == str(other)
        return NotImplemented
    
    def __hash__(self) -> int:
        return hash(self._value)


class MessageID:
    """
    Type-safe wrapper for Discord message snowflake IDs.
    
    Discord snowflakes are 64-bit integers, but are often stored/transmitted as strings
    for JSON compatibility. This class provides a consistent interface for working with
    message IDs throughout the moderation system.
    
    Attributes:
        _value (str): The snowflake ID stored as a string for JSON parity.
    
    Example:
        >>> mid = MessageID.from_int(123456789012345678)
        >>> mid.to_int()
        123456789012345678
        >>> str(mid)
        '123456789012345678'
        >>> mid = MessageID("123456789012345678")
        >>> mid.to_int()
        123456789012345678
    """
        
    def __init__(self, value: Union[str, int, "MessageID"]) -> None:
        """
        Initialize a MessageID from a string, int, or another MessageID.
        
        Args:
            value: The snowflake ID as a string, int, or MessageID.
        
        Raises:
            ValueError: If the value cannot be converted to a valid snowflake.
        """
        if isinstance(value, MessageID):
            self._value = value._value
        elif isinstance(value, int):
            self._value = str(value)
        elif isinstance(value, str):
            # Validate that it's a valid integer string
            self._value = str(int(value.strip()))
        else:
            raise ValueError(f"Cannot create MessageID from {type(value).__name__}: {value}")
    
    @classmethod
    def from_int(cls, value: int) -> "MessageID":
        """
        Create a MessageID from an integer snowflake.
        
        Args:
            value: The snowflake ID as an integer.
        
        Returns:
            MessageID: A new MessageID instance.
        """
        return cls(value)
    
    @classmethod
    def from_message(cls, message: discord.Message) -> "MessageID":
        """
        Create a MessageID from a Discord Message object.
        
        Args:
            message: The Discord Message to extract the ID from.
        
        Returns:
            MessageID: A new MessageID instance.
        """
        return cls(message.id)
    
    def to_int(self) -> int:
        """
        Convert to an integer for Discord API calls.
        
        Returns:
            int: The snowflake ID as an integer.
        """
        return int(self._value)
    
    def __str__(self) -> str:
        """Return the string representation for JSON serialization."""
        return self._value
    
    def __repr__(self) -> str:
        return f"MessageID({self._value!r})"
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, MessageID):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other
        if isinstance(other, int):
            return self._value == str(other)
        return NotImplemented
    
    def __hash__(self) -> int:
        return hash(self._value)