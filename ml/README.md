# FinPilot AI — ML package (Layer 1 scaffold)

This is a **scaffold only**. Layer 1 implements no features, models, training,
selection logic or market data. It exists so later layers have a typed, linted
and tested home.

## Setup

```powershell
cd ml
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Commands

```powershell
ruff check src tests
ruff format --check src tests
mypy src
pytest
pip-audit --strict
```

No performance numbers, model artefacts or market evidence are produced here.
