from __future__ import annotations
from dataclasses import dataclass
import hashlib

@dataclass(frozen=True, slots=True)
class ImageURL:
    """Immutable wrapper for a Discord image URL."""
    _value: str

    def __post_init__(self):
        url = self._value.strip()
        if not url:
            raise ValueError("ImageURL cannot be empty")
        object.__setattr__(self, "_value", url)

    @classmethod
    def from_url(cls, url: str) -> ImageURL:
        return cls(url)

    def __str__(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"ImageURL({self._value!r})"



@dataclass(frozen=True, slots=True)
class ImageID:
    """Immutable wrapper for an image ID derived from an ImageURL."""
    _value: str

    def __post_init__(self):
        if not self._value:
            raise ValueError("ImageID cannot be empty")

    @classmethod
    def from_url(cls, url: ImageURL) -> ImageID:
        """Create an ImageID from an ImageURL."""
        hashed = hashlib.sha256(str(url).encode("utf-8")).hexdigest()[:8]
        return cls(hashed)

    def __str__(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"ImageID({self._value!r})"
