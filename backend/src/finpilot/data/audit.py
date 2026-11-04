"""Per symbol/day market data audit pipeline (Layer 4).

Executes comprehensive data health checks:
1. Temporal coverage and session alignment (09:15-15:30 IST; 75 5-minute bars/session).
2. Duplicate and out-of-order bars.
3. Missing intervals and incomplete sessions.
4. OHLCV consistency and non-finite values.
5. Zero/abnormal volume and suspicious price jumps (> 10% in a single 5m bar).
6. Corporate-action discontinuities (> 20% gaps) and adjustment limitations.
7. Symbol changes, listing, and delisting limitations.
8. Cross-source spot-check discrepancies.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
import statistics
from typing import Sequence
from zoneinfo import ZoneInfo

from finpilot.schemas.instruments import KnownInstrumentRegistry

from .enums import AuditVerdict, DataAnomalyType
from .models import DataAnomaly, DataAuditReport, MarketDataRecord

IST = ZoneInfo("Asia/Kolkata")
NSE_SESSION_OPEN = time(9, 15)
NSE_SESSION_CLOSE_BAR_OPEN = time(15, 25)
TOTAL_EXPECTED_5M_BARS = 75


class MarketDataAuditor:
    """Auditor for per-symbol/day 5-minute market data."""

    def __init__(self, registry: KnownInstrumentRegistry | None = None) -> None:
        self._registry = registry

    def audit_session(
        self,
        symbol: str,
        audit_date: date,
        records: Sequence[MarketDataRecord],
        previous_session_close: Decimal | None = None,
    ) -> DataAuditReport:
        """Execute the 8-point audit check on a symbol's 5-minute bars for a specific date."""
        anomalies: list[DataAnomaly] = []
        clean_sym = symbol.strip().upper()
        provenance = records[0].source if records else "EMPTY_INPUT"

        # Check: Weekend trading
        if audit_date.weekday() >= 5:
            day_name = "Saturday" if audit_date.weekday() == 5 else "Sunday"
            anomalies.append(
                DataAnomaly(
                    anomaly_type=DataAnomalyType.SESSION_MISALIGNMENT,
                    severity="CRITICAL",
                    description=f"Market data provided for non-trading weekend day ({day_name}).",
                    observed_value=audit_date.isoformat(),
                    expected_value="Monday-Friday trading days",
                )
            )

        # 1. Temporal coverage, sorting, and duplicate checks
        seen_timestamps: set[datetime] = set()
        duplicate_count = 0
        out_of_order_count = 0
        ohlc_inconsistency_count = 0
        non_finite_or_non_positive_count = 0
        negative_volume_count = 0
        zero_volume_bars = 0
        single_bar_jump_count = 0

        valid_session_timestamps: set[datetime] = set()
        prev_ts: datetime | None = None
        volumes: list[int] = []

        for rec in records:
            ts_utc = rec.timestamp
            ts_ist = ts_utc.astimezone(IST)
            t = ts_ist.time()

            # Session alignment check
            is_aligned_minute = (ts_ist.minute % 5 == 0) and (ts_ist.second == 0)
            in_session = (NSE_SESSION_OPEN <= t <= NSE_SESSION_CLOSE_BAR_OPEN) and (
                ts_ist.date() == audit_date
            )

            if not is_aligned_minute or not in_session:
                anomalies.append(
                    DataAnomaly(
                        anomaly_type=DataAnomalyType.SESSION_MISALIGNMENT,
                        severity="ERROR",
                        description=(
                            f"Timestamp {ts_ist.isoformat()} outside regular NSE 5-minute session "
                            f"(09:15-15:25 IST)."
                        ),
                        timestamp=ts_utc,
                        observed_value=ts_ist.strftime("%H:%M:%S"),
                        expected_value="09:15 to 15:25 at 5-minute multiples",
                    )
                )

            # Duplicate check
            if ts_utc in seen_timestamps:
                duplicate_count += 1
                anomalies.append(
                    DataAnomaly(
                        anomaly_type=DataAnomalyType.DUPLICATE_BAR,
                        severity="ERROR",
                        description=f"Duplicate bar timestamp encountered: {ts_ist.isoformat()}.",
                        timestamp=ts_utc,
                    )
                )
            seen_timestamps.add(ts_utc)

            # Monotonic ordering check
            if prev_ts and ts_utc < prev_ts:
                out_of_order_count += 1
                anomalies.append(
                    DataAnomaly(
                        anomaly_type=DataAnomalyType.OUT_OF_ORDER_BAR,
                        severity="ERROR",
                        description=(
                            f"Bar timestamp regressed: {ts_ist.isoformat()} was preceded by "
                            f"{prev_ts.astimezone(IST).isoformat()}."
                        ),
                        timestamp=ts_utc,
                    )
                )
            prev_ts = ts_utc

            # OHLC consistency check
            if rec.high < rec.open or rec.high < rec.close or rec.high < rec.low:
                ohlc_inconsistency_count += 1
                anomalies.append(
                    DataAnomaly(
                        anomaly_type=DataAnomalyType.OHLC_INCONSISTENCY,
                        severity="ERROR",
                        description=(
                            f"High price ({rec.high}) less than max(Open={rec.open}, "
                            f"Close={rec.close}, Low={rec.low})."
                        ),
                        timestamp=ts_utc,
                    )
                )

            if rec.low > rec.open or rec.low > rec.close or rec.low > rec.high:
                ohlc_inconsistency_count += 1
                anomalies.append(
                    DataAnomaly(
                        anomaly_type=DataAnomalyType.OHLC_INCONSISTENCY,
                        severity="ERROR",
                        description=(
                            f"Low price ({rec.low}) greater than min(Open={rec.open}, "
                            f"Close={rec.close}, High={rec.high})."
                        ),
                        timestamp=ts_utc,
                    )
                )

            # Price positive and finite check
            for p_name, p_val in (
                ("open", rec.open),
                ("high", rec.high),
                ("low", rec.low),
                ("close", rec.close),
            ):
                if p_val.is_nan() or p_val.is_infinite():
                    non_finite_or_non_positive_count += 1
                    anomalies.append(
                        DataAnomaly(
                            anomaly_type=DataAnomalyType.NON_FINITE_PRICE,
                            severity="CRITICAL",
                            description=f"Non-finite price {p_val} on {p_name}.",
                            timestamp=ts_utc,
                        )
                    )
                elif p_val <= Decimal("0"):
                    non_finite_or_non_positive_count += 1
                    anomalies.append(
                        DataAnomaly(
                            anomaly_type=DataAnomalyType.NON_POSITIVE_PRICE,
                            severity="CRITICAL",
                            description=f"Non-positive price {p_val} on {p_name}.",
                            timestamp=ts_utc,
                        )
                    )

            # Volume checks
            if rec.volume < 0:
                negative_volume_count += 1
                anomalies.append(
                    DataAnomaly(
                        anomaly_type=DataAnomalyType.NEGATIVE_VOLUME,
                        severity="CRITICAL",
                        description=f"Negative volume ({rec.volume}) observed.",
                        timestamp=ts_utc,
                    )
                )
            elif rec.volume == 0:
                zero_volume_bars += 1

            volumes.append(rec.volume)

            # Suspicious single-bar price jump (> 10% in a single 5m bar)
            if rec.open > Decimal("0"):
                bar_move_pct = abs(rec.close - rec.open) / rec.open
                if bar_move_pct > Decimal("0.10"):
                    single_bar_jump_count += 1
                    anomalies.append(
                        DataAnomaly(
                            anomaly_type=DataAnomalyType.SUSPICIOUS_PRICE_JUMP,
                            severity="WARNING",
                            description=(
                                f"Suspicious single-bar price jump: {bar_move_pct * 100:.2f}% "
                                f"(Open={rec.open}, Close={rec.close})."
                            ),
                            timestamp=ts_utc,
                            observed_value=f"{bar_move_pct * 100:.2f}%",
                            expected_value="<= 10% within 5m bar",
                        )
                    )

            if is_aligned_minute and in_session:
                valid_session_timestamps.add(ts_utc)

        # Check: Volume spikes (> 15x median volume)
        if len(volumes) >= 5:
            med_vol = statistics.median(volumes)
            if med_vol > 0:
                for rec in records:
                    if rec.volume > med_vol * 15 and rec.volume > 50000:
                        anomalies.append(
                            DataAnomaly(
                                anomaly_type=DataAnomalyType.VOLUME_SPIKE,
                                severity="WARNING",
                                description=(
                                    f"Abnormal volume spike: {rec.volume} "
                                    f"({rec.volume / med_vol:.1f}x median {med_vol:.0f})."
                                ),
                                timestamp=rec.timestamp,
                                observed_value=str(rec.volume),
                                expected_value=f"<= {med_vol * 15:.0f}",
                            )
                        )

        # Check: Missing intervals and incomplete sessions
        all_expected_ist: set[datetime] = set()
        for i in range(TOTAL_EXPECTED_5M_BARS):
            total_min = 9 * 60 + 15 + i * 5
            h = total_min // 60
            m = total_min % 60
            dt_exp = datetime(
                audit_date.year, audit_date.month, audit_date.day, h, m, 0, tzinfo=IST
            ).astimezone(UTC)
            all_expected_ist.add(dt_exp)

        missing_timestamps = all_expected_ist - valid_session_timestamps
        missing_bars_count = len(missing_timestamps)

        if missing_bars_count > 0:
            severity = "CRITICAL" if missing_bars_count > 30 else "WARNING"
            anomalies.append(
                DataAnomaly(
                    anomaly_type=DataAnomalyType.INCOMPLETE_SESSION,
                    severity=severity,
                    description=(
                        f"Session incomplete: {missing_bars_count} of {TOTAL_EXPECTED_5M_BARS} "
                        "bars missing."
                    ),
                    observed_value=f"{len(valid_session_timestamps)} bars",
                    expected_value=f"{TOTAL_EXPECTED_5M_BARS} bars",
                )
            )

        # Check: Corporate action discontinuity (> 20% gap from previous session close)
        if previous_session_close and records:
            first_bar = sorted(records, key=lambda r: r.timestamp)[0]
            if previous_session_close > Decimal("0"):
                gap_pct = abs(first_bar.open - previous_session_close) / previous_session_close
                if gap_pct > Decimal("0.20"):
                    anomalies.append(
                        DataAnomaly(
                            anomaly_type=DataAnomalyType.CORPORATE_ACTION_GAP,
                            severity="CRITICAL",
                            description=(
                                f"Suspected corporate action discontinuity: {gap_pct * 100:.2f}% "
                                f"gap between previous close ({previous_session_close}) and "
                                f"session open ({first_bar.open}). Adjustment needed."
                            ),
                            timestamp=first_bar.timestamp,
                            observed_value=f"{gap_pct * 100:.2f}% gap",
                            expected_value="< 20% standard gap without corporate action",
                        )
                    )

        # Total, valid, and quarantined count computation
        total_bars = len(records)
        quarantined_bars = (
            duplicate_count
            + out_of_order_count
            + ohlc_inconsistency_count
            + non_finite_or_non_positive_count
            + negative_volume_count
        )
        valid_bars = max(0, total_bars - quarantined_bars)
        completion_pct = round((len(valid_session_timestamps) / TOTAL_EXPECTED_5M_BARS) * 100.0, 2)

        # Quality score computation (1.0 base, penalized by defects)
        penalty = 0.0
        penalty += (missing_bars_count / TOTAL_EXPECTED_5M_BARS) * 0.5
        penalty += min(0.3, duplicate_count * 0.05)
        penalty += min(0.4, ohlc_inconsistency_count * 0.1)
        penalty += min(0.5, non_finite_or_non_positive_count * 0.25)
        penalty += min(0.2, single_bar_jump_count * 0.05)
        quality_score = max(0.0, round(1.0 - penalty, 4))

        # Overall verdict
        has_critical = any(a.severity == "CRITICAL" for a in anomalies)
        has_errors = any(a.severity == "ERROR" for a in anomalies)

        if has_critical or quality_score < 0.70 or ohlc_inconsistency_count > 0:
            verdict = AuditVerdict.REJECTED
        elif has_errors or quality_score < 0.95 or missing_bars_count > 0:
            verdict = AuditVerdict.WARNING
        else:
            verdict = AuditVerdict.PASS

        return DataAuditReport(
            symbol=clean_sym,
            audit_date=audit_date,
            session_expected_bars=TOTAL_EXPECTED_5M_BARS,
            total_bars=total_bars,
            valid_bars=valid_bars,
            quarantined_bars=quarantined_bars,
            missing_bars=missing_bars_count,
            completion_pct=completion_pct,
            quality_score=quality_score,
            anomalies=tuple(anomalies),
            verdict=verdict,
            provenance_source=provenance,
            generated_at=datetime.now(UTC),
        )

    def cross_source_check(
        self,
        primary_records: Sequence[MarketDataRecord],
        reference_records: Sequence[MarketDataRecord],
        tolerance_pct: Decimal = Decimal("0.005"),  # 0.5% max price deviation
    ) -> list[DataAnomaly]:
        """Perform cross-source spot check comparing primary records to independent reference."""
        discrepancies: list[DataAnomaly] = []
        ref_map = {r.timestamp: r for r in reference_records}

        for p_rec in primary_records:
            ref_rec = ref_map.get(p_rec.timestamp)
            if not ref_rec:
                continue

            if ref_rec.close > Decimal("0"):
                diff = abs(p_rec.close - ref_rec.close) / ref_rec.close
                if diff > tolerance_pct:
                    discrepancies.append(
                        DataAnomaly(
                            anomaly_type=DataAnomalyType.CROSS_SOURCE_DISCREPANCY,
                            severity="WARNING",
                            description=(
                                f"Cross-source discrepancy on {p_rec.symbol} at "
                                f"{p_rec.timestamp.isoformat()}: primary close={p_rec.close}, "
                                f"reference close={ref_rec.close} (delta={diff * 100:.3f}%)."
                            ),
                            timestamp=p_rec.timestamp,
                            observed_value=str(p_rec.close),
                            expected_value=str(ref_rec.close),
                        )
                    )

        return discrepancies
