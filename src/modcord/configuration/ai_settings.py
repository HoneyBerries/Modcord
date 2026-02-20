from typing import Any, Dict


class AISettings:
    """Helper exposing typed accessors for AI configuration.

    This class provides accessors for OpenAI-compatible API settings:
    - base_url: The API endpoint URL
    - api_key: The API key for authentication
    - model_name: The model identifier to use
    - system_prompt: The system prompt template
    """

    def __init__(self, data: Dict[str, Any] | None = None) -> None:
        self.data: Dict[str, Any] = data or {}

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for `key` or `default` if missing."""
        return self.data.get(key, default)

    def as_dict(self) -> Dict[str, Any]:
        """Return the underlying mapping (shallow copy recommended by callers)."""
        return self.data

    @property
    def base_url(self) -> str:
        """Return the OpenAI-compatible API base URL."""
        return str(self.data.get("base_url", "http://localhost:8000/v1"))

    @property
    def model_name(self) -> str:
        """Return the model name/identifier to use for inference."""
        return str(self.data.get("model_name", ""))