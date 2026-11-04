"""Data provider adapters package (Layer 4)."""

from __future__ import annotations

from .base import BaseDataProviderAdapter
from .bhavcopy import NseBhavcopyAdapter
from .file_adapter import CsvFileAdapter, ParquetFileAdapter
from .synthetic import SyntheticDataProviderAdapter

__all__ = [
    "BaseDataProviderAdapter",
    "CsvFileAdapter",
    "NseBhavcopyAdapter",
    "ParquetFileAdapter",
    "SyntheticDataProviderAdapter",
]
