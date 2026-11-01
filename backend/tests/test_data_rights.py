"""Data rights matrix and research governance tests (Layer 4)."""

from __future__ import annotations

from pathlib import Path


def test_data_rights_matrix_audit_status() -> None:
    matrix_path = Path("docs/data-rights-matrix.md")
    assert matrix_path.exists(), "docs/data-rights-matrix.md must exist."

    content = matrix_path.read_text(encoding="utf-8")

    # 1. Unverified public scrape sources must be explicitly BLOCKED
    assert "Kaggle / Hugging Face" in content
    assert "Yahoo Finance" in content
    assert "**BLOCKED**" in content

    # 2. NSE Bhavcopy permitted for internal research, BLOCKED for public display/redistribution
    assert "NSE Official Bhavcopy" in content
    assert "BLOCKED for redistribution/public display" in content

    # 3. Synthetic demo fixtures permitted with mandatory label
    assert "SYNTHETIC DEMO" in content
    assert "Strictly labelled SYNTHETIC DEMO; never market evidence" in content

    # 4. Seven standardized use cases covered
    for use_case in (
        "Private Research",
        "Hosted Notebook Processing",
        "Model Training",
        "Forward Paper Simulation",
        "Public Display",
        "Redistribution",
        "Derived Outputs",
    ):
        assert use_case in content, f"Missing standardized use case: {use_case}"
