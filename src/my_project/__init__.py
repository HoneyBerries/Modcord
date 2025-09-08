"""
Compatibility package to expose existing src/ modules under the new package name `my_project`.
This file contains lightweight re-export modules so tests and external imports can use
`my_project.*` while the original code remains in `src/`.
"""
# Intentionally left minimal; individual module files under this package re-export
# the implementation from the original `src` package.
__all__ = []

