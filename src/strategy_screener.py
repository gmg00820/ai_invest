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
        res_df.attrs['total_candidates'] = len(res_df)
        res_df = res_df.head(30) # 상위 30개
    else:
        res_df.attrs['total_candidates'] = 0
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
        res_df.attrs['total_candidates'] = len(res_df)
        res_df = res_df.head(30)
    else:
        res_df.attrs['total_candidates'] = 0
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
    factor_df.attrs['total_candidates'] = len(factor_df)
    top_count = min(30, max(5, int(len(factor_df) * 0.2)))
    factor_df = factor_df.head(top_count)
    
    # 불필요한 열 정리 및 가독성
    factor_df['스코어'] = factor_df['스코어'].round(1)
    display_cols = ["종목명", "티커", "테마(업종)", "현재가", "스코어"]
    return factor_df[display_cols]


def run_longterm_magic_strategy(tickers_data: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    """
    롱텀 매직 (Long-term Magic) — 원래 요구사항 기반 엄격한 조건 검색
    
    [공통 전제 필터]
      F1: 이평선 정배열 — MA(5) > MA(20) AND MA(20) >= MA(60)
      F2: 장기 추세   — Close > MA(240) OR MA(60) 기울기 양수
      F3: 유동성     — MarketCap >= 1,000억 원
    
    [수렴 조건 (Volatility Squeeze)]
      S1: 단기 수렴 — ABS(MA5 - MA20) / MA20 < 0.03
      S2: 중기 수렴 — ABS(MA20 - MA60) / MA60 < 0.05
    
    [진입 전략]
      Case A (돌파 매수): Close > MAX(High, 20) AND Volume > AvgVolume(20) * 3.0
      Case B (눌림 매수): Close가 MA20 근처 접근 AND Volume > AvgVolume(20) * 1.5
    
    스코어 100점 만점 / 70점 이상만 표출 / 모든 조건 충족 시 ⭐ 표시
    """
    results = []
    
    for ticker, data in tickers_data.items():
        df = data.get('df')
        marcap = data.get('marcap', 0)
        
        if df is None or len(df) < 60:
            continue
            
        # --- F3: 유동성 필터 (시총 1000억 미만 제외) ---
        if marcap > 0:
            if marcap < 100_000_000_000:
                continue
        else:
            if 'value' in df.columns:
                val_ma20 = sma(df['value'], length=20).iloc[-1]
            else:
                val_ma20 = (df['close'] * df['volume']).rolling(20, min_periods=5).mean().iloc[-1]
            if pd.isna(val_ma20) or val_ma20 < 3_000_000_000:
                continue
                
        close = df['close']
        open_p = df['open']
        high = df['high']
        low = df['low']
        volume = df['volume']
        current_close = close.iloc[-1]
        
        # 이동평균선 계산
        ma5 = sma(close, length=5)
        ma20 = sma(close, length=20)
        ma60 = sma(close, length=60)
        ma120 = sma(close, length=120)  # MA240 대용 (KIS API 100일 데이터 제한)
        avg_vol_20 = sma(volume, length=20)
        
        if pd.isna(ma5.iloc[-1]) or pd.isna(ma20.iloc[-1]) or pd.isna(ma60.iloc[-1]):
            continue
            
        # 20일 최고가 (전일까지)
        max_high_20 = high.shift(1).rolling(window=20, min_periods=10).max()
        
        # --- 최근 5일간 탐색: 각 날짜별 조건 체크 ---
        best_signal_score = 0.0
        best_signal_type = ""
        is_perfect = False
        
        lookback_days = min(6, len(close))
        
        for i in range(1, lookback_days + 1):
            idx = -i
            
            total_score = 0.0
            f1_pass = False
            f2_pass = False
            s1_pass = False
            s2_pass = False
            entry_type = ""
            
            v5 = ma5.iloc[idx]
            v20 = ma20.iloc[idx]
            v60 = ma60.iloc[idx]
            v120 = ma120.iloc[idx] if not pd.isna(ma120.iloc[idx]) else None
            c_close = close.iloc[idx]
            c_vol = volume.iloc[idx]
            a_vol_20 = avg_vol_20.iloc[idx]
            
            # ========== F1: 이평선 정배열 (Max 20점) ==========
            # 완벽 정배열: MA5 > MA20 >= MA60 → 20점
            # 부분 정배열: MA5 > MA20 (MA60 미충족) → 10점
            if v5 > v20 and v20 >= v60:
                total_score += 20.0
                f1_pass = True
            elif v5 > v20:
                total_score += 10.0
            # 역배열이면 0점
            
            # ========== F2: 장기 추세 (Max 15점) ==========
            # Close > MA240(또는 MA120 대용) → 10점
            # MA60 기울기 양수 → 5점
            f2_long_trend = False
            if v120 is not None and c_close > v120:
                total_score += 10.0
                f2_long_trend = True
            
            # MA60 기울기 체크
            if len(ma60) >= abs(idx) + 2:
                ma60_prev = ma60.iloc[idx - 1]
                if not pd.isna(ma60_prev) and v60 > ma60_prev:
                    total_score += 5.0
                    if not f2_long_trend:
                        f2_long_trend = True
            
            f2_pass = f2_long_trend
            
            # ========== S1: 단기 수렴 (Max 15점) ==========
            # |MA5 - MA20| / MA20 < 0.03 → 15점 만점
            # 0.03~0.05 → 부분 점수
            s1_ratio = abs(v5 - v20) / v20 if v20 > 0 else 1.0
            if s1_ratio < 0.03:
                total_score += 15.0
                s1_pass = True
            elif s1_ratio < 0.05:
                total_score += 15.0 * (0.05 - s1_ratio) / 0.02  # 선형 감소
            # 0.05 이상이면 0점
            
            # ========== S2: 중기 수렴 (Max 15점) ==========
            # |MA20 - MA60| / MA60 < 0.05 → 15점 만점
            # 0.05~0.08 → 부분 점수
            s2_ratio = abs(v20 - v60) / v60 if v60 > 0 else 1.0
            if s2_ratio < 0.05:
                total_score += 15.0
                s2_pass = True
            elif s2_ratio < 0.08:
                total_score += 15.0 * (0.08 - s2_ratio) / 0.03  # 선형 감소
            # 0.08 이상이면 0점
            
            # ========== 진입 전략 (Max 35점) ==========
            c_max_20 = max_high_20.iloc[idx]
            c_open = open_p.iloc[idx]
            vol_ratio = c_vol / a_vol_20 if (not pd.isna(a_vol_20) and a_vol_20 > 0) else 0
            
            case_a = False
            case_b = False
            
            # --- Case A: 돌파 매수 (Max 35점) ---
            # A1: Close > MAX(High, 20) AND A2: Volume > AvgVolume(20) * 3.0
            if not pd.isna(c_max_20) and c_close > c_max_20 and vol_ratio >= 3.0:
                total_score += 35.0
                entry_type = "돌파 매수(A)"
                case_a = True
            elif not pd.isna(c_max_20) and c_close > c_max_20 and vol_ratio >= 2.0:
                # 돌파했지만 거래량이 3배 미만 → 부분 점수
                total_score += 20.0 + (vol_ratio - 2.0) * 15.0  # 2배→20점, 3배→35점
                entry_type = "돌파 후보(A-)"
            elif not pd.isna(c_max_20) and c_close > c_max_20:
                # 돌파했지만 거래량 부족
                total_score += 10.0
                entry_type = "약돌파(A--)"
            
            # --- Case B: 눌림 매수 (Max 25점, Case A 미충족 시) ---
            if not case_a:
                # B1: Close가 MA20 근처 (±3% 이내) AND B2: Volume > AvgVolume(20) * 1.5
                prox_ma20 = abs(c_close - v20) / v20 if v20 > 0 else 1.0
                if prox_ma20 <= 0.03 and vol_ratio >= 1.5 and c_close >= c_open:
                    total_score += 25.0
                    entry_type = "눌림 매수(B)"
                    case_b = True
                elif prox_ma20 <= 0.05 and vol_ratio >= 1.2 and c_close >= c_open:
                    # 근접 조건 부분 충족
                    total_score += 12.0
                    entry_type = "눌림 후보(B-)"
            
            if total_score > best_signal_score:
                best_signal_score = total_score
                
                # 완벽 조건: F1 + F2 + S1 + S2 + (Case A 또는 Case B 완전 충족)
                perfect_condition = f1_pass and f2_pass and s1_pass and s2_pass and (case_a or case_b)
                day_str = "오늘" if i == 1 else f"{i-1}일전"
                
                if perfect_condition:
                    best_signal_type = f"{entry_type}({day_str}) ⭐"
                    is_perfect = True
                else:
                    if entry_type:
                        best_signal_type = f"{entry_type}({day_str})"
                    else:
                        best_signal_type = f"조건부합({day_str})"
                    is_perfect = False
                    
        # 필터링 최소 점수컷: 70점 이상만 표출하여 변별력 확보
        if best_signal_score < 70.0:
            continue
            
        name_display = data.get("name")
        if is_perfect:
            name_display = f"⭐ {name_display}"
            
        results.append({
            "종목명": name_display,
            "티커": ticker,
            "테마(업종)": data.get("theme", "기타"),
            "진입전략": best_signal_type,
            "스코어": round(best_signal_score, 1),
            "시가총액(억)": int(marcap / 100_000_000),
            "현재가": int(current_close)
        })
        
    res_df = pd.DataFrame(results)
    if not res_df.empty:
        res_df = res_df.sort_values("스코어", ascending=False).reset_index(drop=True)
        res_df.attrs['total_candidates'] = len(res_df)
        res_df = res_df.head(20)
    else:
        res_df.attrs['total_candidates'] = 0
    return res_df

def run_pullback_breakout_strategy(tickers_data: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    """
    전략5: 눌림목 & 급등 전조 (Pullback & Pre-Breakout)
    1. Uptrend Filter (Pass/Fail): 60일선 > 120일선
    2. Prior Strength (Max 20): 최근 30일 내 고점 형성 강도
    3. Pullback Proximity (Max 35): 고점 대비 -7% ~ -20% 조정 및 20일/60일선 ±5% 이내 접근
    4. Volume Exhaustion (Max 30): 최근 3일 평균 거래량이 20일 평균 대비 대폭 감소
    5. Volatility Contraction (Max 15): NR7 패턴 출현 시 가점
    """
    results = []
    
    for ticker, data in tickers_data.items():
        df = data.get('df')
        # KIS API는 100일치를 기본 제공하므로 125일 제한을 걸면 100% 필터링됩니다.
        if df is None or len(df) < 60:
            continue
            
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        current_close = close.iloc[-1]
        
        # 0. Uptrend Filter (Pass/Fail)
        ma60 = sma(close, length=60)
        ma120 = sma(close, length=120)
        
        if pd.isna(ma60.iloc[-1]) or pd.isna(ma120.iloc[-1]):
            continue
            
        if ma60.iloc[-1] <= ma120.iloc[-1]:
            continue # 하락추세 제외
            
        # 1. Prior Strength (Max 20)
        recent_high_30 = high.rolling(30).max().iloc[-1]
        recent_low_30 = low.rolling(30).min().iloc[-1]
        
        if pd.isna(recent_high_30) or recent_low_30 == 0:
            continue
            
        rise_pct = (recent_high_30 - recent_low_30) / recent_low_30
        score_strength = min(20.0, rise_pct * 40.0) # 50% 이상 상승했으면 20점 만점
        
        # 2. Pullback Proximity (Max 35)
        # 2-1. 조정 폭 (-7% ~ -20% 구간 이상적)
        pullback_depth = (current_close - recent_high_30) / recent_high_30
        
        if -0.25 <= pullback_depth <= -0.05:
            # -0.07 ~ -0.20을 15점 만점으로 채점
            if -0.20 <= pullback_depth <= -0.07:
                score_depth = 15.0
            else:
                score_depth = 7.0
        else:
            score_depth = 0.0
            
        # 2-2. 이평선 근접도 (MA20 또는 MA60에 ±5% 이내)
        ma20 = sma(close, length=20).iloc[-1]
        ma60_val = ma60.iloc[-1]
        
        prox_ma20 = abs(current_close - ma20) / ma20 if ma20 > 0 else 1.0
        prox_ma60 = abs(current_close - ma60_val) / ma60_val if ma60_val > 0 else 1.0
        
        best_prox = min(prox_ma20, prox_ma60)
        
        if best_prox <= 0.05:
            # ±5% 이내면 점수 부여 (0%에 가까울수록 20점 만점)
            score_prox = 20.0 * (1.0 - (best_prox / 0.05))
        else:
            score_prox = 0.0
            
        score_pullback = score_depth + score_prox
        
        # 3. Volume Exhaustion (Max 30)
        vol_ma3 = volume.rolling(3).mean().iloc[-1]
        vol_ma20 = volume.rolling(20).mean().iloc[-1]
        
        if pd.isna(vol_ma3) or vol_ma20 == 0:
            score_vol = 0.0
        else:
            vol_ratio = vol_ma3 / vol_ma20
            # 50% 이하일 때 만점 가까이
            if vol_ratio <= 0.5:
                score_vol = 30.0
            elif vol_ratio <= 1.0:
                score_vol = 30.0 * (1.0 - vol_ratio) * 2.0
            else:
                score_vol = 0.0
                
        # 4. Volatility Contraction (NR7 - Max 15)
        daily_ranges = high - low
        recent_7d_ranges = daily_ranges.tail(7)
        
        score_nr7 = 0.0
        if len(recent_7d_ranges) == 7:
            current_range = recent_7d_ranges.iloc[-1]
            min_range = recent_7d_ranges.min()
            
            if current_range == min_range and current_range > 0:
                score_nr7 = 15.0
                
        total_score = score_strength + score_pullback + score_vol + score_nr7
        
        # 유동성 필터 (잡주 제거)
        if 'value' in df.columns:
            val_ma20 = sma(df['value'], length=20).iloc[-1]
        else:
            val_ma20 = (close * volume).rolling(20, min_periods=5).mean().iloc[-1]
            
        if pd.isna(val_ma20) or val_ma20 <= 3_000_000_000:
            continue
            
        # 총점이 너무 낮으면 제외 (예: 40점 이상)
        if total_score < 40.0:
            continue
            
        signal_type = "눌림목 후보"
        if score_prox >= 10.0 and score_nr7 == 15.0 and score_vol >= 15.0:
            signal_type = "🎯 막 뜨기 직전(NR7)"
            
        results.append({
            "종목명": data.get("name"),
            "티커": ticker,
            "테마(업종)": data.get("theme", "기타"),
            "진입전략": signal_type,
            "스코어": round(total_score, 1),
            "조정폭(%)": round(pullback_depth * 100, 1),
            "현재가": int(current_close) if current_close > 100 else current_close
        })
        
    res_df = pd.DataFrame(results)
    if not res_df.empty:
        res_df = res_df.sort_values("스코어", ascending=False).reset_index(drop=True)
        res_df.attrs['total_candidates'] = len(res_df)
        res_df = res_df.head(30)
    else:
        res_df.attrs['total_candidates'] = 0
    return res_df
