"""
Compatibility package that makes the `modcord` package importable from the project root
by pointing the package import path to the implementation under `src/modcord`.
This lets existing tests and scripts which import `modcord.*` continue to work while
keeping the real implementation inside `src/modcord/`.
"""
from pathlib import Path
import sys

# Determine the src/modcord implementation directory relative to repository root
HERE = Path(__file__).resolve().parent
SRC_IMPL = HERE.parent / "src" / "modcord"

if SRC_IMPL.exists():
    # Prepend to __path__ so Python will search the implementation directory for submodules
    __path__.insert(0, str(SRC_IMPL))
else:
    # If the expected location doesn't exist, fall back to system behavior.
    # This will allow normal import errors to surface.
    pass
