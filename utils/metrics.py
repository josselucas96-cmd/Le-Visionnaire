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


def monthly_returns_table(port_index: pd.Series, spy_index: pd.Series) -> pd.DataFrame:
    """Month-by-month returns for portfolio and SPY, sorted newest first."""
    def to_monthly(s):
        monthly = s.resample("ME").last()
        return monthly.pct_change().dropna() * 100

    port_m = to_monthly(port_index).rename("Portfolio")
    spy_m  = to_monthly(spy_index).rename("S&P 500") if spy_index is not None and not spy_index.empty else pd.Series(name="S&P 500")

    df = pd.concat([port_m, spy_m], axis=1).dropna(how="all")
    df.index = df.index.strftime("%b %Y")
    df["Alpha"] = df["Portfolio"] - df["S&P 500"]
    return df.iloc[::-1]  # newest first


def annualized_volatility(returns: pd.Series) -> float | None:
    if returns.empty or len(returns) < 5:
        return None
    return round(returns.std() * np.sqrt(252) * 100, 2)


def var_95(returns: pd.Series) -> float | None:
    """Historical VaR 95% — worst daily loss at 5th percentile."""
    if returns.empty or len(returns) < 20:
        return None
    return round(np.percentile(returns, 5) * 100, 2)


def avg_pairwise_correlation(history: pd.DataFrame, positions: list) -> float | None:
    """Average of all off-diagonal correlation coefficients."""
    tickers = [p["ticker"] for p in positions if p["ticker"] in history.columns]
    if len(tickers) < 2:
        return None
    returns = history[tickers].pct_change().dropna(how="all")
    corr = returns.corr()
    # Extract upper triangle (excluding diagonal)
    mask = np.triu(np.ones(corr.shape), k=1).astype(bool)
    values = corr.where(mask).stack()
    return round(float(values.mean()), 2)


def correlation_matrix(history: pd.DataFrame, positions: list) -> pd.DataFrame:
    """Daily return correlation between all positions with sufficient history."""
    tickers = [p["ticker"] for p in positions if p["ticker"] in history.columns]
    if len(tickers) < 2:
        return pd.DataFrame()
    returns = history[tickers].pct_change().dropna(how="all")
    return returns.corr().round(2)
