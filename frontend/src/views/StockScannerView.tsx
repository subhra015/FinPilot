/**
 * Stock Scanner View (Layer 13).
 *
 * Point-in-time universe explorer with causal features, 5-minute bar aggregation,
 * causal relative volume (never full-day volume), and session geometry filters.
 */

import React, { useEffect, useState } from "react";
import { fetchScannedStocks, ScannedStock } from "../api/services";
import { useDataMode } from "../context/ModeContext";

interface StockScannerViewProps {
  onSelectSymbol?: (symbol: string) => void;
}

export const StockScannerView: React.FC<StockScannerViewProps> = ({ onSelectSymbol }) => {
  const { modeLabel } = useDataMode();
  const [stocks, setStocks] = useState<ScannedStock[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [filterEligibleOnly, setFilterEligibleOnly] = useState(true);

  useEffect(() => {
    let mounted = true;
    fetchScannedStocks()
      .then((res) => {
        if (mounted) {
          setStocks(res);
          setLoading(false);
        }
      })
      .catch(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const filteredStocks = stocks.filter((stock) => {
    const matchesSearch =
      stock.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
      stock.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesEligibility = !filterEligibleOnly || stock.isEligiblePIT;
    return matchesSearch && matchesEligibility;
  });

  return (
    <div className="view-container" role="region" aria-label="Stock Scanner View">
      <div className="view-header">
        <div>
          <h2>Stock Scanner & Causal Features</h2>
          <p className="subtitle">
            Point-in-time eligible universe with strictly causal intraday feature calculation.
          </p>
        </div>
        <div className="mode-tag-pill" data-testid="scanner-mode-tag">
          Mode: <strong>{modeLabel}</strong>
        </div>
      </div>

      {/* Causal Geometry Notice */}
      <div className="alert-card alert-warning">
        <h4>Causal Volume & Session Isolation Guarantees</h4>
        <p>
          Relative volume (RVOL) is calculated <strong>strictly against historical comparable intraday time intervals</strong> (e.g., prior session bars up to 10:15 IST). It never peeks forward into eventual full-day volume. Warm-up counters guarantee indicator stability before signal eligibility.
        </p>
      </div>

      {/* Controls & Search */}
      <div className="controls-row">
        <div className="search-box">
          <label htmlFor="stock-search" className="sr-only">Search stock</label>
          <input
            id="stock-search"
            type="text"
            className="input-text"
            placeholder="Search symbol or name (e.g., TCS, INFY)..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="checkbox-control">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={filterEligibleOnly}
              onChange={(e) => setFilterEligibleOnly(e.target.checked)}
            />
            Point-in-Time Eligible Only
          </label>
        </div>

        <div className="session-status-badge">
          Session Window: <strong>09:15 - 15:30 IST</strong> | Entry Cutoff: <strong>14:30 IST</strong>
        </div>
      </div>

      {/* Stocks Table */}
      {loading ? (
        <div className="loading-spinner">Loading scanner universe...</div>
      ) : (
        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Company</th>
                <th>Last Price (₹)</th>
                <th>Change %</th>
                <th>RSI (14)</th>
                <th>ATR (14)</th>
                <th>Causal RVOL</th>
                <th>VWAP Dist %</th>
                <th>Session Time</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredStocks.map((stock) => (
                <tr key={stock.symbol}>
                  <td><strong>{stock.symbol}</strong></td>
                  <td>{stock.name}</td>
                  <td>₹{stock.lastPrice.toFixed(2)}</td>
                  <td className={stock.changePct >= 0 ? "text-positive" : "text-negative"}>
                    {stock.changePct >= 0 ? "+" : ""}{stock.changePct.toFixed(2)}%
                  </td>
                  <td>{stock.rsi14.toFixed(1)}</td>
                  <td>₹{stock.atr14.toFixed(2)}</td>
                  <td>
                    <span className={`badge ${stock.causalRelativeVolume >= 1.2 ? "badge-success" : "badge-neutral"}`}>
                      {stock.causalRelativeVolume.toFixed(2)}x
                    </span>
                  </td>
                  <td className={stock.vwapDistancePct >= 0 ? "text-positive" : "text-negative"}>
                    {stock.vwapDistancePct >= 0 ? "+" : ""}{stock.vwapDistancePct.toFixed(2)}%
                  </td>
                  <td>{stock.sessionTimeIST}</td>
                  <td>
                    <button
                      type="button"
                      className="btn-secondary btn-sm"
                      onClick={() => onSelectSymbol && onSelectSymbol(stock.symbol)}
                      data-testid={`inspect-btn-${stock.symbol}`}
                    >
                      Propose Trade
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
