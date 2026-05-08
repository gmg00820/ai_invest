import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Dict, Any, Tuple

def check_ma20_condition(df: pd.DataFrame) -> bool:
    """1. 주가가 20일 이동평균선 위에 있는지 확인"""
    if len(df) < 20:
        return False
    ma20 = ta.sma(df['close'], length=20)
    current_price = df['close'].iloc[-1]
    current_ma20 = ma20.iloc[-1]
    
    if pd.isna(current_ma20):
        return False
    return current_price > current_ma20

def check_surge_condition(df: pd.DataFrame) -> bool:
    """2. 최근 3일 내에 45% 이상 급등한 적이 있는지 확인 (True면 제외 대상)"""
    if len(df) < 4:
        return False
    
    # 3일 전 종가 기준으로, 최근 3일(오늘 포함)의 최고가 등락률 계산
    price_3_days_ago = df['close'].iloc[-4]
    highest_recent = df['high'].iloc[-3:].max()
    
    surge_rate = (highest_recent - price_3_days_ago) / price_3_days_ago * 100
    return surge_rate >= 45.0

def check_volume_value_condition(df: pd.DataFrame) -> bool:
    """
    4. 거래대금 500억 이상 (50,000,000,000 KRW)
       거래량은 시장평균(종목의 20일 평균)에서 +-10% 내외 검사
    """
    if len(df) < 21:
        return False
        
    current_value = df['value'].iloc[-1]
    if pd.isna(current_value) or current_value < 50_000_000_000:
        return False
        
    current_volume = df['volume'].iloc[-1]
    # 이전 20일간의 평균 거래량 계산
    avg_volume = df['volume'].iloc[-21:-1].mean()
    
    if pd.isna(avg_volume) or avg_volume == 0:
        return False
        
    # 거래량이 평균의 +-10% 내외 (0.9 ~ 1.1)
    if not (0.9 * avg_volume <= current_volume <= 1.1 * avg_volume):
        return False
        
    return True

def calculate_envelope(df: pd.DataFrame, length=20, percentage=20) -> Dict[str, float]:
    """5. Envelope 지수 하단/상단/중심선 계산"""
    if len(df) < length:
        return {}
        
    sma = ta.sma(df['close'], length=length)
    env_upper = sma * (1 + percentage / 100)
    env_lower = sma * (1 - percentage / 100)
    
    return {
        "env_upper": env_upper.iloc[-1],
        "env_center": sma.iloc[-1],
        "env_lower": env_lower.iloc[-1]
    }

def analyze_elliott_wave_approx(df: pd.DataFrame) -> Dict[str, Any]:
    """
    6. 엘리어트 파동 근사치 분석
    MACD 히스토그램과 단기 추세를 보조 지표로 사용하여
    현재 상승 3파/5파 계열인지 조정파인지 근사적으로 판별합니다.
    """
    if len(df) < 30:
        return {"wave_status": "Unknown", "score": 0}
        
    macd = ta.macd(df['close'])
    if macd is None or len(macd) < 1:
        return {"wave_status": "Unknown", "score": 0}
        
    hist = macd['MACDh_12_26_9']
    if hist.isna().all():
        return {"wave_status": "Unknown", "score": 0}
        
    # 최근 5일 히스토그램 확인
    recent_hist = hist.iloc[-5:].values
    is_rising = all(recent_hist[i] < recent_hist[i+1] for i in range(len(recent_hist)-1) if not pd.isna(recent_hist[i]))
    
    score = 0
    status = "N/A"
    
    if is_rising and recent_hist[-1] > 0:
        status = "상승 파동 (Impulsive) 추정"
        score = 80
    elif not is_rising and recent_hist[-1] < 0:
        status = "하락/조정 파동 (Corrective) 추정"
        score = 40
    else:
        status = "혼조세 또는 파동 초기"
        score = 60
        
    return {
        "wave_status": status,
        "score": score
    }

def filter_asset(df: pd.DataFrame) -> Tuple[bool, Dict[str, Any]]:
    """모든 조건(1~6)을 순차적으로 통과하는지 필터링하는 파이프라인"""
    if df is None or df.empty:
        return False, {"reason": "No Data"}
        
    if not check_ma20_condition(df):
        return False, {"reason": "주가 20일선 아래"}
        
    if check_surge_condition(df):
        return False, {"reason": "최근 3일 내 45% 이상 급등하여 위험"}
        
    if not check_volume_value_condition(df):
        return False, {"reason": "거래대금 500억 미만 또는 거래량이 평균 +-10% 범위를 벗어남"}
        
    env = calculate_envelope(df)
    wave = analyze_elliott_wave_approx(df)
    
    # 조건을 모두 만족한 경우
    return True, {
        "current_price": df['close'].iloc[-1],
        "envelope": env,
        "wave": wave,
        "reason": "조건 충족"
    }
