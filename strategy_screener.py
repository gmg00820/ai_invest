import pandas as pd
import numpy as np
from typing import Dict, Any

# --- 내장 기술적 지표 계산 함수 (pandas_ta 대체용) ---
def sma(series, length):
    return series.rolling(window=length, min_periods=max(1, length//3)).mean()

def stdev(series, length):
    return series.rolling(window=length, min_periods=max(2, length//3)).std()

def rsi(series, length=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ema_up = up.ewm(com=length-1, adjust=False, min_periods=max(1, length//2)).mean()
    ema_down = down.ewm(com=length-1, adjust=False, min_periods=max(1, length//2)).mean()
    rs = ema_up / ema_down
    return 100 - (100 / (1 + rs))

def atr(high, low, close, length=14):
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=length, min_periods=max(1, length//3)).mean()

def get_20d_high(df: pd.DataFrame) -> pd.Series:
    return df['high'].shift(1).rolling(window=20, min_periods=5).max()

# ---------------------------------------------------

def run_mean_reversion(tickers_data: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    results = []
    
    for ticker, data in tickers_data.items():
        df = data.get('df')
        # 데이터가 너무 적으면 통과
        if df is None or len(df) < 40:
            continue
            
        close = df['close']
        open_p = df['open']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        # 기본 스코어
        total_score = 0.0
        
        # 1. 과매도 (Z-score)
        ma20 = sma(close, length=20)
        std20 = stdev(close, length=20)
        std20 = std20.replace(0, np.nan)
        z_score = (close - ma20) / std20
        current_z = z_score.iloc[-1] if not pd.isna(z_score.iloc[-1]) else 0
        
        # Z값이 마이너스일수록 큰 점수 부여 (예: Z=-2 면 30점, Z=-3 이면 45점)
        if current_z < 0:
            total_score += max(0, -current_z * 15)
            
        # 2. 모멘텀 보조 (RSI)
        rsi14 = rsi(close, length=14)
        recent_rsi = rsi14.iloc[-5:].min() if not pd.isna(rsi14.iloc[-5:].min()) else 50
        # RSI가 낮을수록 가점 (30 이하면 10점, 20이면 20점)
        total_score += max(0, (40 - recent_rsi))
        
        # 3. 추세 필터
        ma120 = sma(close, length=120)
        ma60 = sma(close, length=60)
        
        current_close = close.iloc[-1]
        
        # 이평선 정배열 또는 추세 유지중이면 가산점 20점
        current_ma120 = ma120.iloc[-1]
        if not pd.isna(current_ma120) and current_close > current_ma120:
            total_score += 20
        else:
            if len(ma60) >= 2 and not pd.isna(ma60.iloc[-1]) and not pd.isna(ma60.iloc[-2]):
                if ma60.iloc[-1] > ma60.iloc[-2]:
                    total_score += 20
                    
        # 4. 보조 필터
        vol_ma20 = sma(volume, length=20).iloc[-1]
        current_vol = volume.iloc[-1]
        if not pd.isna(vol_ma20) and vol_ma20 > 0:
            if current_vol > vol_ma20 * 1.5:
                # 거래량이 폭발적이면 15점 가산점
                total_score += 15
                
        # 갭하락 시가 (낙폭 과대 시그널)
        if len(close) > 1 and open_p.iloc[-1] < close.iloc[-2] * 0.98:
            total_score += 15
            
        # 5. 하한선 유동성 필터 (잡주 제거)
        if 'value' in df.columns:
            val_ma20 = sma(df['value'], length=20).iloc[-1]
        else:
            val_ma20 = (close * volume).rolling(20, min_periods=5).mean().iloc[-1]
            
        if pd.isna(val_ma20) or val_ma20 <= 3_000_000_000: # 30억 미만 제외
            continue
            
        results.append({
            "종목명": data.get("name"),
            "티커": ticker,
            "테마(업종)": data.get("theme", "기타"),
            "스코어": round(total_score, 1),
            "Z-Score": round(current_z, 2),
            "RSI(최저)": round(recent_rsi, 1),
            "현재가": current_close
        })
        
    res_df = pd.DataFrame(results)
    if not res_df.empty:
        res_df = res_df.sort_values("스코어", ascending=False).reset_index(drop=True)
        res_df = res_df.head(30) # 상위 30개
    return res_df


def run_volatility_breakout(tickers_data: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    results = []
    
    for ticker, data in tickers_data.items():
        df = data.get('df')
        if df is None or len(df) < 40:
            continue
            
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        total_score = 0.0
        
        # 1. 변동성 수축 가점 (낮을수록 점수 높음)
        atr14_val = atr(high, low, close, length=14).iloc[-1]
        atr60_val = atr(high, low, close, length=60).iloc[-1]
        
        atr_ratio = atr14_val / atr60_val if not pd.isna(atr60_val) and atr60_val > 0 else 1.0
        # 0.9 이하면 가산점 (0.7 이하면 20점)
        total_score += max(0, (0.9 - atr_ratio) * 100)
        
        # 2. 거래량 확장 가점
        vol_ma20 = sma(volume, length=20).iloc[-1]
        current_vol = volume.iloc[-1]
        vol_ratio = current_vol / vol_ma20 if not pd.isna(vol_ma20) and vol_ma20 > 0 else 0
        # 최대 40점
        total_score += max(0, min(40, (vol_ratio - 1) * 10))
        
        # 3. 가격 돌파 강도 가점
        recent_high_20 = get_20d_high(df).iloc[-1]
        current_close = close.iloc[-1]
        breakout_strength = (current_close - recent_high_20) / recent_high_20 * 100 if not pd.isna(recent_high_20) and recent_high_20 > 0 else 0
        
        # 신고가를 갱신하면 팍 점수오름, 아닐경우 약간 마이너스
        if breakout_strength > 0:
            total_score += min(40, breakout_strength * 4) # 10% 돌파면 40점 만점
        else:
            total_score += breakout_strength # 아직 돌파 못했으면 깎임
            
        # 유동성 필터
        if 'value' in df.columns:
            val_ma20 = sma(df['value'], length=20).iloc[-1]
        else:
            val_ma20 = (close * volume).rolling(20, min_periods=5).mean().iloc[-1]
            
        if pd.isna(val_ma20) or val_ma20 <= 3_000_000_000:
            continue
            
        results.append({
            "종목명": data.get("name"),
            "티커": ticker,
            "테마(업종)": data.get("theme", "기타"),
            "스코어": round(total_score, 1),
            "돌파강도(%)": round(breakout_strength, 2),
            "ATR비율": round(atr_ratio, 2),
            "현재가": current_close
        })
        
    res_df = pd.DataFrame(results)
    if not res_df.empty:
        res_df = res_df.sort_values("스코어", ascending=False).reset_index(drop=True)
        res_df = res_df.head(30)
    return res_df


def run_multi_factor(tickers_data: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    raw_factors = []
    
    for ticker, data in tickers_data.items():
        df = data.get('df')
        fund = data.get('fundamentals', {})
        
        if df is None or len(df) < 40: # 125 제한을 40으로 완화하여 데이터 누락 방지
            continue
            
        close = df['close']
        current_close = close.iloc[-1]
        
        # Momentum: 가용 가능한 최대 구간 수익률 산정 (120일 또는 그 최적)
        lookback = min(120, len(close)-1)
        price_120d_ago = close.iloc[-lookback - 1] if len(close) > lookback else close.iloc[0]
        momentum = (current_close - price_120d_ago) / price_120d_ago if price_120d_ago > 0 else 0
        
        # Low Volatile: 60 days volatility
        vol_lookback = min(60, len(close))
        vol_60d = close.iloc[-vol_lookback:].pct_change().std()
        
        # Value & Quality
        per = fund.get('PER', 0)
        pbr = fund.get('PBR', 0)
        
        value_factor = 1.0 / per if (pd.notna(per) and per > 0) else np.nan
        roe_factor = (pbr / per) * 100 if (pd.notna(per) and pd.notna(pbr) and per > 0) else np.nan
        
        raw_factors.append({
            "종목명": data.get("name"),
            "티커": ticker,
            "테마(업종)": data.get("theme", "기타"),
            "현재가": current_close,
            "Value": value_factor,
            "Quality": roe_factor,
            "Momentum": momentum,
            "Volatility": vol_60d
        })
        
    factor_df = pd.DataFrame(raw_factors)
    if factor_df.empty:
        return factor_df
        
    # 결측치 처리 (중간값으로 대체) - 팩터 모형이 텅 비는것을 방지
    for col in ["Value", "Quality", "Momentum", "Volatility"]:
        factor_df[col] = factor_df[col].fillna(factor_df[col].median())
        
    # Z-Score 표준화 변환
    def z_score(series):
        std = series.std()
        if std == 0 or pd.isna(std):
            return pd.Series(np.zeros(len(series)))
        return (series - series.mean()) / std

    factor_df['Z_Value'] = z_score(factor_df['Value'])
    factor_df['Z_Quality'] = z_score(factor_df['Quality'])
    factor_df['Z_Momentum'] = z_score(factor_df['Momentum'])
    factor_df['Z_Volatility'] = z_score(factor_df['Volatility']) # 낮은게 좋으므로 역산 필요
    
    # Growth 배분된 가중치 적용
    # Value(20%), Quality(32.5%), Momentum(32.5%), LowVol(15%)
    # LowVol은 부호 반전
    factor_df['Score'] = (
        factor_df['Z_Value'] * 0.20 +
        factor_df['Z_Quality'] * 0.325 +
        factor_df['Z_Momentum'] * 0.325 +
        (-factor_df['Z_Volatility']) * 0.15
    )
    
    # 점수 스케일링 (0~100 가시성)
    max_score = factor_df['Score'].max()
    min_score = factor_df['Score'].min()
    if max_score > min_score:
        factor_df['스코어'] = (factor_df['Score'] - min_score) / (max_score - min_score) * 100
    else:
        factor_df['스코어'] = factor_df['Score']
        
    # Score 내림차순 정렬 및 상위 표시
    factor_df = factor_df.sort_values(by='스코어', ascending=False).reset_index(drop=True)
    top_count = min(30, max(5, int(len(factor_df) * 0.2)))
    factor_df = factor_df.head(top_count)
    
    # 불필요한 열 정리 및 가독성
    factor_df['스코어'] = factor_df['스코어'].round(1)
    display_cols = ["종목명", "티커", "테마(업종)", "현재가", "스코어"]
    return factor_df[display_cols]


def run_split_strategy(tickers_data: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    """
    스플릿 전용 (되돌림/회복 로직):
    1. 유동성: 일평균 거래대금 500억 이상, 거래량 100만주 이상
    2. 재무(망하지 않을 기업): PER > 0 (흑자) 및 기본 우량주 필터 적용
    3. 변동성: ATR(14) 3~8%, 52주 변동폭 > 50%, 잦은 테마순환
    """
    results = []
    
    # 테마/섹터 순환이 자주 오는 업종
    target_themes = ["반도체", "전지", "바이오", "방산", "의료", "제약", "로봇", "AI", "인공지능", "엔터", "소프트웨어", "IT"]
    
    for ticker, data in tickers_data.items():
        df = data.get('df')
        fund = data.get('fundamentals', {})
        
        if df is None or len(df) < 60: 
            continue
            
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        current_close = close.iloc[-1]
        
        # 1. 유동성 필터 (최근 20일 기준)
        if 'value' in df.columns:
            val_ma20 = sma(df['value'], length=20).iloc[-1]
        else:
            val_ma20 = (close * volume).rolling(20, min_periods=5).mean().iloc[-1]
            
        vol_ma20 = sma(volume, length=20).iloc[-1]
        
        if pd.isna(val_ma20) or val_ma20 < 50_000_000_000: # 거래대금 500억 이상
            continue
            
        if pd.isna(vol_ma20) or vol_ma20 < 1_000_000: # 거래량 100만주 이상
            continue
            
        # 2. 재무 필터 (PER > 0, 흑자) 
        per = fund.get('PER', 0)
        if pd.isna(per) or per <= 0:
            continue
            
        # 3. 변동성 조건 (ATR 3~8%)
        atr14_val = atr(high, low, close, length=14).iloc[-1]
        atr_pct = (atr14_val / current_close) * 100 if current_close > 0 else 0
        
        if pd.isna(atr_pct) or atr_pct < 3 or atr_pct > 8:
            continue
            
        # 52주 변동폭 > 50%
        lookback = min(250, len(close))
        high_52w = high.iloc[-lookback:].max()
        low_52w = low.iloc[-lookback:].min()
        
        if low_52w <= 0:
            continue
        
        volatility_52w_pct = ((high_52w - low_52w) / low_52w) * 100
        
        if volatility_52w_pct < 50:
            continue
            
        # 스코어링 
        total_score = 0.0
        
        # 변동성이 클수록 가점 
        total_score += min(50, (volatility_52w_pct - 50) * 0.5)
        
        # 현재 낙폭이 클수록 되돌림 여력 증가 (고점 대비 낙폭)
        drawdown_pct = ((high_52w - current_close) / high_52w) * 100
        if drawdown_pct > 30: # 30% 이상 빠졌으면 강한 가점
            total_score += min(50, drawdown_pct)
        else:
            total_score += min(30, drawdown_pct * 0.5)
            
        # 테마 가점
        theme = data.get("theme", "기타")
        if any(t in theme for t in target_themes):
            total_score += 20
            
        results.append({
            "종목명": data.get("name"),
            "티커": ticker,
            "테마(업종)": theme,
            "스코어": round(total_score, 1),
            "일평균대금(억)": int(val_ma20 / 100_000_000),
            "ATR(%)": round(atr_pct, 1),
            "52주변동(%)": round(volatility_52w_pct, 1),
            "고점대비낙폭(%)": round(drawdown_pct, 1),
            "현재가": int(current_close)
        })
        
    res_df = pd.DataFrame(results)
    if not res_df.empty:
        res_df = res_df.sort_values("스코어", ascending=False).reset_index(drop=True)
        res_df = res_df.head(30)
    return res_df
