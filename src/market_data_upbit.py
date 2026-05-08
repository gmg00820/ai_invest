import pyupbit
import pandas as pd
from typing import List, Optional

def get_krw_tickers() -> List[str]:
    """Get all KRW tickers from Upbit."""
    return pyupbit.get_tickers(fiat="KRW")

def get_daily_ohlcv(ticker: str, count: int = 200) -> Optional[pd.DataFrame]:
    """
    Get daily OHLCV data for a ticker.
    Includes open, high, low, close, volume, value (거래대금).
    """
    try:
        # pyupbit returns DataFrame with columns: open, high, low, close, volume, value
        df = pyupbit.get_ohlcv(ticker, interval="day", count=count)
        if df is not None and not df.empty:
            return df
        return None
    except Exception as e:
        print(f"Error fetching Upbit data for {ticker}: {e}")
        return None

def get_weekly_ohlcv(ticker: str, count: int = 100) -> Optional[pd.DataFrame]:
    """Get weekly OHLCV for Elliott Wave analysis"""
    try:
        df = pyupbit.get_ohlcv(ticker, interval="week", count=count)
        return df
    except Exception as e:
        return None

def get_monthly_ohlcv(ticker: str, count: int = 50) -> Optional[pd.DataFrame]:
    """Get monthly OHLCV for Elliott Wave analysis"""
    try:
        df = pyupbit.get_ohlcv(ticker, interval="month", count=count)
        return df
    except Exception as e:
        return None
