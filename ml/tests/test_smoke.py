"""Smoke test for the ML package scaffold (no models are implemented)."""

from __future__ import annotations

from finpilot_ml import PACKAGE_NAME, __version__, describe


def test_describe_returns_package_metadata() -> None:
    info = describe()
    assert info == {"name": PACKAGE_NAME, "version": __version__}
    assert info["name"] == "finpilot-ml"
