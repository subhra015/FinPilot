"""FinPilot AI ML package.

Layer 1 contains no models, features or selection logic. This package exists only
so later layers have a typed, tooled home. No market data or derived evidence is
produced here.
"""

from __future__ import annotations

__version__ = "0.1.0"
PACKAGE_NAME = "finpilot-ml"


def describe() -> dict[str, str]:
    """Return non-sensitive package metadata (plumbing only, not evidence)."""

    return {"name": PACKAGE_NAME, "version": __version__}
