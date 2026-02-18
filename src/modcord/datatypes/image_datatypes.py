from __future__ import annotations
from dataclasses import dataclass
import hashlib

@dataclass(frozen=True, slots=True)
class ImageLink:
    """Immutable wrapper for a Discord image link."""
    _value: str

    def __post_init__(self):
        url = self._value.strip()
        if not url:
            raise ValueError("ImageLink cannot be empty")
        object.__setattr__(self, "_value", url)

    @classmethod
    def from_url(cls, url: str) -> ImageLink:
        return cls(url)

    def __str__(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"ImageLink({self._value!r})"



@dataclass(frozen=True, slots=True)
class ImageID:
    """Immutable wrapper for an image ID derived from an ImageLink."""
    _value: str

    def __post_init__(self):
        if not self._value:
            raise ValueError("ImageID cannot be empty")

    @classmethod
    def from_url(cls, url: ImageLink) -> ImageID:
        """Create an ImageID from an ImageLink."""
        hashed = hashlib.sha256(str(url).encode("utf-8")).hexdigest()[:8]
        return cls(hashed)

    def __str__(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"ImageID({self._value!r})"
