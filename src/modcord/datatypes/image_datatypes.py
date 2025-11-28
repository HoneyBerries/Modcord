from typing import Union


class ImageURL:
    """
    Type-safe wrapper for Discord image URLs.
    
    This class provides a consistent interface for working with image URLs
    throughout the moderation system. URLs are stored as strings and validated
    to ensure they are valid URLs.
    
    Attributes:
        _value (str): The image URL string.
    
    Example:
        >>> url = ImageURL("https://example.com/image.png")
        >>> str(url)
        'https://example.com/image.png'
        >>> url2 = ImageURL.from_url("https://example.com/image2.png")
    """
    
    __slots__ = ("_value",)
    
    def __init__(self, value: Union[str, "ImageURL"]) -> None:
        """
        Initialize an ImageURL from a string or another ImageURL.
        
        Args:
            value: The image URL as a string or ImageURL.
        
        Raises:
            ValueError: If the value is empty or not a valid string.
        """
        if isinstance(value, ImageURL):
            self._value = value._value
        elif isinstance(value, str):
            url = value.strip()
            if not url:
                raise ValueError("ImageURL cannot be empty")
            self._value = url
        else:
            raise ValueError(f"Cannot create ImageURL from {type(value).__name__}: {value}")
    
    @classmethod
    def from_url(cls, url: str) -> "ImageURL":
        """
        Create an ImageURL from a URL string.
        
        Args:
            url: The image URL as a string.
        
        Returns:
            ImageURL: A new ImageURL instance.
        
        Raises:
            ValueError: If the URL is empty or invalid.
        """
        return cls(url)
    
    def to_string(self) -> str:
        """
        Get the URL as a string.
        
        Returns:
            str: The image URL.
        """
        return self._value
    
    def __str__(self) -> str:
        """Return the string representation for JSON serialization."""
        return self._value
    
    def __repr__(self) -> str:
        return f"ImageURL({self._value!r})"
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, ImageURL):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other
        return NotImplemented
    
    def __hash__(self) -> int:
        return hash(self._value)




class ImageID:
    """
    Type-safe wrapper for image IDs (SHA256 hash prefixes).
    
    This class provides a consistent interface for working with image IDs
    throughout the moderation system. IDs are stored as strings representing
    the first 8 characters of a SHA256 hash of the image URL.
    
    Attributes:
        _value (str): The image ID string.
    
    Example:
        >>> img_id = ImageID("abc12345")
        >>> str(img_id)
        'abc12345'
    """
    
    __slots__ = ("_value",)
    
    def __init__(self, value: Union[str, "ImageID"]) -> None:
        """
        Initialize an ImageID from a string or another ImageID.
        
        Args:
            value: The image ID as a string or ImageID.
        
        Raises:
            ValueError: If the value is empty or not a valid string.
        """
        if isinstance(value, ImageID):
            self._value = value._value
        elif isinstance(value, str):
            img_id = value.strip()
            if not img_id:
                raise ValueError("ImageID cannot be empty")
            self._value = img_id
        else:
            raise ValueError(f"Cannot create ImageID from {type(value).__name__}: {value}")
    
    def to_string(self) -> str:
        """
        Get the ID as a string.
        
        Returns:
            str: The image ID.
        """
        return self._value
    
    def __str__(self) -> str:
        """Return the string representation for JSON serialization."""
        return self._value
    
    def __repr__(self) -> str:
        return f"ImageID({self._value!r})"
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, ImageID):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other
        return NotImplemented
    
    def __hash__(self) -> int:
        return hash(self._value)
    