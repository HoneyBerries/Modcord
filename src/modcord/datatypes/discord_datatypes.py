from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar, Type, Union
import discord

SnowflakeT = TypeVar("SnowflakeT", bound="DiscordSnowflake")


class DiscordSnowflake:
    """
    An immutable canonical Discord snowflake value object.
    
    Discord snowflakes are unique 64-bit integers used as IDs. They are 
    composed of a timestamp, internal worker ID, internal process ID, 
    and an increment. This class wraps that value to ensure consistency 
    and provide type-safe operations.
    """

    __slots__ = ("_value",)

    def __init__(self, value: Union[str, int, "DiscordSnowflake"]) -> None:
        """
        Initializes a new DiscordSnowflake.

        Args:
            value: The ID value. Can be a string, integer, or another 
                DiscordSnowflake instance.

        Raises:
            TypeError: If the value provided is not a supported type.
            ValueError: If a string value cannot be converted to an integer.
        """
        if isinstance(value, DiscordSnowflake):
            normalized = value._value
        elif isinstance(value, int):
            normalized = str(value)
        elif isinstance(value, str):
            # Ensure it's a valid integer string
            normalized = str(int(value.strip()))
        else:
            raise TypeError(f"Invalid snowflake type: {type(value).__name__}")
    

        # Bypass immutability guard using object.__setattr__
        object.__setattr__(self, "_value", normalized)

    # -------------------------
    # Immutability Enforcement
    # -------------------------

    def __setattr__(self, key, value):
        """
        Prevents modification of the instance attributes.

        Raises:
            AttributeError: Always raised to enforce immutability.
        """
        raise AttributeError(
            f"{self.__class__.__name__} really does not want you to modify its attributes."
        )

    # -------------------------
    # Constructors
    # -------------------------

    @classmethod
    def from_int(cls: Type[SnowflakeT], value: int) -> SnowflakeT:
        """Creates a snowflake instance from a raw integer."""
        return cls(value)

    @classmethod
    def from_discord(cls: Type[SnowflakeT], obj: discord.abc.Snowflake) -> SnowflakeT:
        """
        Creates a snowflake instance from a discord.py model.

        Args:
            obj: Any Discord object that implements the Snowflake interface 
                (e.g., discord.User, discord.Message).
        """
        return cls(obj.id)


    # -------------------------
    # Representation
    # -------------------------

    def __str__(self) -> str:
        """Returns the string representation of the snowflake ID."""
        return self._value
    
    def __int__(self) -> int:
        """Returns the integer representation of the snowflake ID."""
        return int(self._value)

    def __repr__(self) -> str:
        """Returns a developer-friendly representation of the snowflake."""
        return f"{self.__class__.__name__}({self._value!r})"

    # -------------------------
    # Comparison
    # -------------------------

    def __eq__(self, other: Any) -> bool:
        """
        Compares this snowflake with another object.
        
        Supports comparison against other DiscordSnowflake instances 
        or raw strings.
        """
        if isinstance(other, DiscordSnowflake):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other
        return NotImplemented

    def __hash__(self) -> int:
        """Returns the hash of the snowflake for use in sets or as dict keys."""
        return hash(self._value)


# ==========================
# Specific Snowflake Types
# ==========================

class UserID(DiscordSnowflake):
    """Specialized Snowflake for Discord User or Member IDs."""
    
    @classmethod
    def from_user(cls, user: Union[discord.User, discord.Member]) -> "UserID":
        """Creates a UserID from a discord.User or discord.Member object."""
        return cls.from_discord(user)


class GuildID(DiscordSnowflake):
    """Specialized Snowflake for Discord Guild (Server) IDs."""
    @classmethod
    def from_guild(cls, guild: discord.Guild) -> "GuildID":
        """Creates a GuildID from a discord.Guild object."""
        return cls.from_discord(guild)


class ChannelID(DiscordSnowflake):
    """Specialized Snowflake for Discord Channel IDs."""
    @classmethod
    def from_channel(cls, channel: discord.abc.Snowflake) -> "ChannelID":
        """Creates a ChannelID from any Discord channel object."""
        return cls.from_discord(channel)


class MessageID(DiscordSnowflake):
    """Specialized Snowflake for Discord Message IDs."""
    @classmethod
    def from_message(cls, message: discord.Message) -> "MessageID":
        """Creates a MessageID from a discord.Message object."""
        return cls.from_discord(message)
    


# ==================

# ==================

@dataclass(frozen=True, slots=True)
class DiscordUsername:
    """Immutable wrapper for a Discord username with associated user ID."""
    user_id: UserID
    username: str

    def __post_init__(self):
        name = self.username.strip()
        if not name:
            object.__setattr__(self, "username", "<Unknown User>")
        else:
            object.__setattr__(self, "username", name)

    @classmethod
    def from_member(cls, member: discord.Member | discord.User) -> DiscordUsername:
        """Construct from a Discord Member or User object."""
        return cls(user_id=UserID.from_user(member), username=str(member))

    def __str__(self) -> str:
        return self.username

    def __repr__(self) -> str:
        return f"DiscordUsername(user_id={self.user_id!r}, username={self.username!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, DiscordUsername):
            return self.user_id == other.user_id
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.user_id)