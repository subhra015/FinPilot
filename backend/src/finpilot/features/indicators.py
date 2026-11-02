"""Pure, causal mathematical indicator implementations (Layer 5).

Governed by:
- DATA_AND_PERFORMANCE_POLICY.md §2 (Point-in-Time Correctness)
- ARCHITECTURE.md §2 (Feature Pipeline)
- Layer 5 Gate: Causal features from completed candles only.
"""

from __future__ import annotations


def calculate_return(closes: list[float], period: int = 1) -> float | None:
    """Calculate causal percentage price return over `period` completed bars.

    Formula: (Close_t - Close_{t-period}) / Close_{t-period}
    Returns None if fewer than (period + 1) bars are provided.
    """
    if period <= 0 or len(closes) < period + 1:
        return None
    prev = closes[-period - 1]
    if prev <= 0.0:
        return None
    return (closes[-1] - prev) / prev


def calculate_sma(closes: list[float], period: int) -> float | None:
    """Calculate Simple Moving Average over `period` completed bars.

    Returns None if fewer than `period` bars are provided.
    """
    if period <= 0 or len(closes) < period:
        return None
    return sum(closes[-period:]) / float(period)


def calculate_rsi(closes: list[float], period: int = 14) -> float | None:
    """Calculate causal Relative Strength Index (RSI) over `period` completed bars.

    Uses standard 14-period window. Returns None if fewer than (period + 1) bars exist.
    Range: [0.0, 100.0].
    """
    if period <= 0 or len(closes) < period + 1:
        return None

    # Calculate bar-to-bar price differences for the last `period` transitions
    diffs = [
        closes[i] - closes[i - 1]
        for i in range(len(closes) - period, len(closes))
    ]

    gains = [d if d > 0.0 else 0.0 for d in diffs]
    losses = [-d if d < 0.0 else 0.0 for d in diffs]

    avg_gain = sum(gains) / float(period)
    avg_loss = sum(losses) / float(period)

    if avg_loss == 0.0:
        if avg_gain == 0.0:
            return 50.0  # Completely flat price
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return float(max(0.0, min(100.0, rsi)))


def calculate_true_range(
    high: float, low: float, prev_close: float | None
) -> float:
    """Calculate True Range for a bar given current high, low, and previous close.

    TR = max(H - L, |H - C_{prev}|, |L - C_{prev}|)
    If prev_close is None (e.g. first bar), TR = H - L.
    """
    hl = high - low
    if prev_close is None:
        return hl
    hc = abs(high - prev_close)
    lc = abs(low - prev_close)
    return max(hl, hc, lc)


def calculate_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float | None:
    """Calculate Average True Range (ATR) over `period` completed bars.

    Returns None if fewer than `period` bars exist.
    """
    n = len(closes)
    if period <= 0 or n < period or len(highs) < n or len(lows) < n:
        return None

    tr_values: list[float] = []
    for i in range(n - period, n):
        prev_c = closes[i - 1] if i > 0 else None
        tr = calculate_true_range(highs[i], lows[i], prev_c)
        tr_values.append(tr)

    return sum(tr_values) / float(period)


def calculate_vwap_approx(
    typical_prices: list[float],
    volumes: list[int],
) -> float | None:
    """Calculate intraday OHLCV session VWAP approximation.

    Formula: sum(TypicalPrice_i * Volume_i) / sum(Volume_i)
    Strictly within the current session (resets to 0 at session start).
    Returns None if total session volume is 0.
    """
    if not typical_prices or not volumes or len(typical_prices) != len(volumes):
        return None

    total_tp_vol = 0.0
    total_vol = 0
    for tp, v in zip(typical_prices, volumes, strict=True):
        total_tp_vol += tp * v
        total_vol += v

    if total_vol <= 0:
        return None
    return total_tp_vol / float(total_vol)


def calculate_causal_relative_volume(
    current_volume: int,
    prior_volumes: list[int],
    window: int = 10,
) -> float | None:
    """Calculate causal relative volume using strictly prior completed periods.

    Formula: CurrentVolume / mean(PriorVolumes[-window:])
    CRITICAL CAUSAL INVARIANT:
    `prior_volumes` MUST NOT contain `current_volume` or any future bar volume.
    Never uses eventual full-day volume for a morning signal.
    """
    if window <= 0 or len(prior_volumes) < window:
        return None

    recent_prior = prior_volumes[-window:]
    mean_prior = sum(recent_prior) / float(window)

    if mean_prior <= 0.0:
        if current_volume <= 0:
            return 1.0
        return 1.0

    return float(current_volume) / mean_prior


def calculate_turnover_proxy(close: float, volume: int) -> float:
    """Calculate 5-minute bar turnover proxy in INR: Close * Volume."""
    return float(close) * float(volume)
