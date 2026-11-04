"""Deterministic synthetic market data provider for demo and software tests (Layer 4).

Generates strictly labelled SYNTHETIC_DEMO 5-minute completed bars.
Never to be presented as real-market evidence.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
import hashlib
import math
from typing import Sequence
from zoneinfo import ZoneInfo

from finpilot.db.enums import CurrencyCode, DataMode, ExchangeCode
from finpilot.schemas.datasets import DataSourceMetadata
from finpilot.schemas.instruments import KnownInstrumentRegistry

from ..enums import AdjustmentStatus, QualityFlag
from ..models import MarketDataRecord
from .base import BaseDataProviderAdapter

IST = ZoneInfo("Asia/Kolkata")
NSE_SESSION_OPEN = time(9, 15)
TOTAL_5M_BARS_PER_SESSION = 75  # 09:15, 09:20, ..., 15:25 (75 bars total)


class SyntheticDataProviderAdapter(BaseDataProviderAdapter):
    """Adapter producing reproducible, realistic NSE synthetic 5-minute candle bars."""

    def __init__(
        self,
        registry: KnownInstrumentRegistry | None = None,
        base_prices: dict[str, Decimal] | None = None,
    ) -> None:
        self._registry = registry or KnownInstrumentRegistry({"RELIANCE": 101, "TCS": 102, "INFY": 103})
        self._base_prices = base_prices or {
            "RELIANCE": Decimal("2500.0000"),
            "TCS": Decimal("3800.0000"),
            "INFY": Decimal("1600.0000"),
        }

    @property
    def provider_source(self) -> str:
        return "SYNTHETIC_DEMO"

    @property
    def data_mode(self) -> DataMode:
        return DataMode.SYNTHETIC_DEMO

    def get_provider_metadata(self) -> DataSourceMetadata:
        now = datetime.now(UTC)
        prov_hash = hashlib.sha256(b"FINPILOT_SYNTHETIC_GENERATOR_V1").hexdigest()
        return DataSourceMetadata(
            source_id="SYNTHETIC_DEMO_GEN",
            provider_name="FinPilot Synthetic Generator",
            terms_verified=True,
            license_reference="FinPilot MIT/Internal Self-Generated Synthetic Fixture License",
            fetch_timestamp=now,
            provenance_hash=prov_hash,
        )

    def fetch_bars(self, symbol: str, target_date: date) -> Sequence[MarketDataRecord]:
        """Generate a complete, valid session of 75 5-minute bars for the target date."""
        # Weekend check
        if target_date.weekday() >= 5:
            return []

        clean_sym = symbol.strip().upper()
        inst_id = self._registry.resolve_instrument_id(clean_sym)
        base_price = self._base_prices.get(clean_sym, Decimal("1000.0000"))

        records: list[MarketDataRecord] = []
        now = datetime.now(UTC)
        current_price = base_price

        # Pseudo-random deterministic generator based on symbol and date
        seed_str = f"{clean_sym}:{target_date.isoformat()}"
        seed_int = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)

        for bar_idx in range(TOTAL_5M_BARS_PER_SESSION):
            total_minutes = 9 * 60 + 15 + bar_idx * 5
            bar_hour = total_minutes // 60
            bar_min = total_minutes % 60
            dt_ist = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                bar_hour,
                bar_min,
                0,
                tzinfo=IST,
            )
            dt_utc = dt_ist.astimezone(UTC)

            # Deterministic oscillation
            osc = math.sin((seed_int % 1000) + bar_idx * 0.15) * 2.5
            delta = Decimal(str(round(osc, 4)))
            open_p = max(Decimal("1.0000"), current_price)
            close_p = max(Decimal("1.0000"), open_p + delta)
            high_p = max(open_p, close_p) + Decimal("1.2500")
            low_p = max(Decimal("0.5000"), min(open_p, close_p) - Decimal("1.1000"))
            volume = 5000 + int(abs(math.cos(bar_idx * 0.2)) * 10000)

            rec = MarketDataRecord(
                source=self.provider_source,
                retrieval_time=now,
                exchange=ExchangeCode.NSE,
                instrument_id=inst_id,
                symbol=clean_sym,
                timestamp=dt_utc,
                open=open_p.quantize(Decimal("0.0001")),
                high=high_p.quantize(Decimal("0.0001")),
                low=low_p.quantize(Decimal("0.0001")),
                close=close_p.quantize(Decimal("0.0001")),
                volume=volume,
                currency=CurrencyCode.INR,
                adjustment_status=AdjustmentStatus.UNADJUSTED,
                quality_flags=(QualityFlag.CLEAN,),
                mode=self.data_mode,
            )
            records.append(rec)
            current_price = close_p

        return records
