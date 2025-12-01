from typing import Any, Dict

class AISettings:
    """Helper exposing typed accessors for AI tuning configuration.

    This class intentionally provides a minimal, explicit API (`get`,
    `as_dict`, and convenience properties) and does not implement the full
    mapping protocol. Callers that previously relied on mapping behavior
    should use the explicit helpers.
    """

    def __init__(self, data: Dict[str, Any] | None = None) -> None:
        self.data: Dict[str, Any] = data or {}

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for `key` or `default` if missing."""
        return self.data.get(key, default)

    def as_dict(self) -> Dict[str, Any]:
        """Return the underlying mapping (shallow copy recommended by callers)."""
        return self.data

    # Commonly used fields exposed as properties for convenience
    @property
    def enabled(self) -> bool:
        return bool(self.data.get("enabled", False))

    @property
    def allow_gpu(self) -> bool:
        return bool(self.data.get("allow_gpu", False))

    @property
    def vram_percentage(self) -> float:
        return float(self.data.get("vram_percentage", 0.5))

    @property
    def model_id(self) -> str | None:
        val = self.data.get("model_id")
        return str(val) if val else None

    @property
    def sampling_parameters(self) -> Dict[str, Any]:
        k = self.data.get("sampling_parameters", {})
        return k if isinstance(k, dict) else {}

    @property
    def cpu_offload_gb(self) -> int:
        return int(self.data.get("cpu_offload_gb", 0))