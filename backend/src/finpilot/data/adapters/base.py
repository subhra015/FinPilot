"""Provider-agnostic market data adapter interface (Layer 4)."""

from __future__ import annotations

import abc
from datetime import date
from typing import Sequence

from finpilot.db.enums import DataMode
from finpilot.schemas.datasets import DataSourceMetadata

from ..models import MarketDataRecord


class BaseDataProviderAdapter(abc.ABC):
    """Abstract base adapter establishing the provider-agnostic market data interface."""

    @property
    @abc.abstractmethod
    def provider_source(self) -> str:
        """Unique identifier of the data provider source."""

    @property
    @abc.abstractmethod
    def data_mode(self) -> DataMode:
        """The data operating mode for records emitted by this adapter."""

    @abc.abstractmethod
    def fetch_bars(self, symbol: str, target_date: date) -> Sequence[MarketDataRecord]:
        """Fetch completed 5-minute bars for a symbol on a specific trading day."""

    @abc.abstractmethod
    def get_provider_metadata(self) -> DataSourceMetadata:
        """Return the legal, licensing, and provenance metadata for this provider."""
