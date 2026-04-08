import numpy as np
import pandas as pd


def build_portfolio_index(history: pd.DataFrame, positions: list) -> pd.Series:
    """
    Reconstruct a base-100 portfolio index from inception.

    Each position is normalized to 100 from its entry_date.
    Before entry_date the position contributes a flat 100 (i.e. no drag, no gain).
    The final portfolio index is the weight-averaged combination of all positions.

    This is a buy-and-hold simulation — weights are fixed at initiation.
    """
    if history.empty or not positions:
        return pd.Series(dtype=float)

    total_weight = sum(p["weight"] for p in positions)
    if total_weight == 0:
        return pd.Series(dtype=float)

    portfolio = pd.Series(0.0, index=history.index)

    for p in positions:
        ticker = p["ticker"]
        if ticker not in history.columns:
            continue

        w = p["weight"] / total_weight
        series = history[ticker].dropna()
        if series.empty:
            continue

        entry_date = pd.Timestamp(p["entry_date"])

        # Prices from entry date onward
        after = series[series.index >= entry_date]
        if after.empty:
            continue

        base_price = after.iloc[0]
        normalized_after = after / base_price * 100

        # Before entry date: flat at 100 (no position, no P&L)
        before_index = series.index[series.index < entry_date]
        normalized_before = pd.Series(100.0, index=before_index)

        full = pd.concat([normalized_before, normalized_after])
        full = full.reindex(history.index).ffill().bfill()

        portfolio += full * w

    return portfolio


def daily_returns(index: pd.Series) -> pd.Series:
    return index.pct_change().dropna()


def sharpe_ratio(returns: pd.Series, risk_free_annual: float = 0.05) -> float | None:
    if returns.empty or returns.std() == 0:
        return None
    rf_daily = risk_free_annual / 252
    excess = returns - rf_daily
    return round(excess.mean() / excess.std() * np.sqrt(252), 2)


def max_drawdown(index: pd.Series) -> float | None:
    if index.empty:
        return None
    peak = index.cummax()
    dd = (index - peak) / peak
    return round(dd.min() * 100, 2)


def beta_vs_spy(port_returns: pd.Series, spy_returns: pd.Series) -> float | None:
    aligned = pd.concat([port_returns, spy_returns], axis=1).dropna()
    if len(aligned) < 10:
        return None
    cov = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1])
    return round(cov[0][1] / cov[1][1], 2)


def monthly_returns_table(port_index: pd.Series) -> pd.DataFrame:
    """Monthly returns pivoted: years as rows, months Jan-Dec as columns."""
    MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly = port_index.resample("ME").last().pct_change().dropna() * 100
    monthly.index = pd.to_datetime(monthly.index)
    df = pd.DataFrame({
        "year":  monthly.index.year,
        "month": monthly.index.month,
        "ret":   monthly.values,
    })
    pivot = df.pivot(index="year", columns="month", values="ret")
    pivot.columns = [MONTHS[m - 1] for m in pivot.columns]
    # Ensure all 12 months present
    for m in MONTHS:
        if m not in pivot.columns:
            pivot[m] = float("nan")
    pivot = pivot[MONTHS]
    pivot.index.name = None
    return pivot.iloc[::-1]  # newest year first


def annualized_volatility(returns: pd.Series) -> float | None:
    if returns.empty or len(returns) < 5:
        return None
    return round(returns.std() * np.sqrt(252) * 100, 2)


def var_95(returns: pd.Series) -> float | None:
    """Historical VaR 95% — worst daily loss at 5th percentile."""
    if returns.empty or len(returns) < 20:
        return None
    return round(np.percentile(returns, 5) * 100, 2)


def _trailing_returns(history: pd.DataFrame, tickers: list, lookback_days: int = 252) -> pd.DataFrame:
    """Daily returns for the trailing lookback_days window."""
    cutoff = history.index[-1] - pd.Timedelta(days=lookback_days)
    window = history[history.index >= cutoff][tickers]
    return window.pct_change().dropna(how="all")


def avg_pairwise_correlation(history: pd.DataFrame, positions: list) -> float | None:
    """Average of all off-diagonal correlation coefficients — trailing 12 months."""
    tickers = [p["ticker"] for p in positions if p["ticker"] in history.columns]
    if len(tickers) < 2:
        return None
    returns = _trailing_returns(history, tickers)
    if len(returns) < 10:
        return None
    corr = returns.corr()
    mask = np.triu(np.ones(corr.shape), k=1).astype(bool)
    values = corr.where(mask).stack()
    return round(float(values.mean()), 2)


def correlation_matrix(history: pd.DataFrame, positions: list) -> pd.DataFrame:
    """Daily return correlation — trailing 12 months."""
    tickers = [p["ticker"] for p in positions if p["ticker"] in history.columns]
    if len(tickers) < 2:
        return pd.DataFrame()
    returns = _trailing_returns(history, tickers)
    if len(returns) < 10:
        return pd.DataFrame()
    return returns.corr().round(2)
