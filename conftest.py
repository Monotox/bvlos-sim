"""Pytest session configuration.

Pins the embedded tool version to a fixed placeholder so golden fixtures are
version-agnostic: a release version bump (Ticket 098) never invalidates them, and
releasing can no longer break the golden suite. The live version is asserted
separately in ``tests/test_bump_version.py``.
"""

import os

from adapters.version import TOOL_VERSION_ENV

# Set before any test imports an adapter that renders tool_version().
os.environ.setdefault(TOOL_VERSION_ENV, "0.0.0-test")
