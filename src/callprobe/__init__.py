"""callprobe: test whether a model can actually call your tools."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("callprobe")
except PackageNotFoundError:  # running from a source checkout, not installed
    __version__ = "0.0.0+unknown"
