import pandas as pd
import numpy as np
from scipy.signal import find_peaks
from typing import Dict, Any, List

class BaseCondition:
    def __init__(self, name: str, weight: float = 1.0, is_active: bool = True, is_strict: bool = False):
        self.name = name
        self.weight = weight
        self.is_active = is_active
        self.is_strict = is_strict # True면 이 조건을 실패할 경우 즉시 종목 리스트에서 제외

    def evaluate(self, df: pd.DataFrame, ticker: str = "", idx: int = -1, current_score: float = 0.0, fund_data: dict = None) -> tuple[bool, float, str]:
        raise NotImplementedError

# 0. 급등 제외 조건 (Strict 필터)
class SurgeExcludeCondition(BaseCondition):
    def __init__(self, weight=0.0, is_active=True, max_surge_rate=45.0):
        # 점수는 안주지만, 필터링용(Strict)
        super().__init__("급등제외(3일간 45%이하)", weight, is_active, is_strict=True)
        self.max_surge_rate = max_surge_rate
        
    def evaluate(self, df: pd.DataFrame, ticker: str = "", idx: int = -1, current_score: float = 0.0, fund_data: dict = None) -> tuple[bool, float, str]:
        if len(df) < 4:
            return False, 0.0, "데이터 부족(4일 미만)"
            
        target_idx = len(df) - 1 if idx == -1 else idx
        
        # 3일 전 종가 (idx-3) 기준으로 최대가 등락률 확인
        if target_idx - 3 < 0:
            return False, 0.0, "과거 3일 데이터 부족"
            
        price_3_days_ago = df['close'].iloc[target_idx - 3]
        highest_recent = df['high'].iloc[target_idx-2 : target_idx+1].max()
        
        surge_rate = (highest_recent - price_3_days_ago) / price_3_days_ago * 100
        
        # 45% "미만"으로 올랐어야 통과(True), 45% 이상 급등했으면 실패(False)
        passed = bool(surge_rate < self.max_surge_rate)
        
        reason = f"최근 3일 최고상승률 {surge_rate:.1f}% (안전)" if passed else f"최근 3일 최고상승률 {surge_rate:.1f}% 초과(제외)"
        return passed, 0.0, reason

# 1. 거래 조건
class VolumeValueCondition(BaseCondition):
    def __init__(self, weight=30.0, is_active=True, min_vol_ratio=2.0, min_value=50000000000):
        super().__init__("거래조건(거래량/대금)", weight, is_active)
        self.min_vol_ratio = min_vol_ratio # 100% 증가 = 2배
        self.min_value = min_value
        
    def evaluate(self, df: pd.DataFrame, ticker: str = "", idx: int = -1, current_score: float = 0.0, fund_data: dict = None) -> tuple[bool, float, str]:
        if len(df) < 20:
            return False, 0.0, "데이터 부족(20일 미만)"
            
        vol_ma20 = df['volume'].rolling(window=20).mean().iloc[idx]
        current_vol = df['volume'].iloc[idx]
        
        if 'value' in df.columns:
            trade_value = df['value'].iloc[idx]
        else:
            trade_value = df['close'].iloc[idx] * current_vol
            
        if pd.isna(vol_ma20) or vol_ma20 == 0:
            return False, 0.0, "거래량 평균 계산 불가"
            
        is_vol_passed = current_vol >= vol_ma20 * self.min_vol_ratio
        is_val_passed = trade_value >= self.min_value
        passed = bool(is_vol_passed and is_val_passed)
        
        score = self.weight if passed else 0.0
        reason = f"거래량 {current_vol/vol_ma20:.1f}x, 대금 {trade_value/1e8:.0f}억"
        return passed, score, reason

# 2. 추세 조건
class TrendCondition(BaseCondition):
    def __init__(self, weight=20.0, is_active=True):
        super().__init__("추세조건(MA20)", weight, is_active)

    def evaluate(self, df: pd.DataFrame, ticker: str = "", idx: int = -1, current_score: float = 0.0, fund_data: dict = None) -> tuple[bool, float, str]:
        if len(df) < 20:
            return False, 0.0, "데이터 부족(20일 미만)"
            
        ma20 = df['close'].rolling(window=20).mean()
        current_close = df['close'].iloc[idx]
        current_ma20 = ma20.iloc[idx]
        
        target_idx_prev = idx - 1 if idx < 0 else idx - 1
        if target_idx_prev < 0 and idx >= 0:
            target_idx_prev = 0
            
        prev_ma20 = ma20.iloc[target_idx_prev] if len(ma20) > abs(idx) + 1 else current_ma20
        
        if pd.isna(current_ma20) or pd.isna(prev_ma20):
            return False, 0.0, "MA20 계산 불가"
            
        passed = bool((current_close > current_ma20) and (current_ma20 > prev_ma20))
        
        score = self.weight if passed else 0.0
        reason = f"주가>MA20({current_close>current_ma20}), 추세상승({current_ma20>prev_ma20})"
        return passed, score, reason

# 3. 기술적 지표 조건
class TechnicalCondition(BaseCondition):
    def __init__(self, weight=20.0, is_active=True):
        super().__init__("기술적지표(Env/MACD)", weight, is_active)

    def evaluate(self, df: pd.DataFrame, ticker: str = "", idx: int = -1, current_score: float = 0.0, fund_data: dict = None) -> tuple[bool, float, str]:
        if len(df) < 30:
            return False, 0.0, "데이터 부족(30일 미만)"
            
        ma20 = df['close'].rolling(window=20).mean().iloc[idx]
        env_upper = ma20 * 1.05
        current_close = df['close'].iloc[idx]
        env_passed = bool(current_close >= env_upper * 0.98)
        
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        
        macd_val = macd.iloc[idx]
        signal_val = signal.iloc[idx]
        
        macd_passed = bool(macd_val > signal_val)
        
        passed = bool(env_passed and macd_passed)
        score = self.weight if passed else 0.0
        reason = f"Env근접: {env_passed}, MACD>Sig: {macd_passed}"
        return passed, score, reason

# 4. 엘리어트 파동 조건 (Heuristic)
class ElliottWaveCondition(BaseCondition):
    def __init__(self, weight=20.0, is_active=True):
        super().__init__("엘리어트파동(N자형상승)", weight, is_active)

    def evaluate(self, df: pd.DataFrame, ticker: str = "", idx: int = -1, current_score: float = 0.0, fund_data: dict = None) -> tuple[bool, float, str]:
        if len(df) < 60:
            return False, 0.0, "데이터 부족(60일 미만)"
            
        start_idx = max(0, len(df) + idx - 60 if idx < 0 else idx - 60)
        end_idx = len(df) + idx + 1 if idx < 0 else idx + 1
        
        recent_closes = df['close'].iloc[start_idx:end_idx].values
        
        if len(recent_closes) < 10:
            return False, 0.0, "데이터 부족"
            
        prominence = recent_closes.mean() * 0.02
        troughs, _ = find_peaks(-recent_closes, distance=5, prominence=prominence)
        
        if len(troughs) >= 2:
            last_low = recent_closes[troughs[-1]]
            prev_low = recent_closes[troughs[-2]]
            is_uptrend_wave = bool(last_low > prev_low)
        else:
            is_uptrend_wave = False
            
        score = self.weight if is_uptrend_wave else 0.0
        reason = "단기 저점 상승 확인" if is_uptrend_wave else "명확한 상승 파동 아님"
        return is_uptrend_wave, score, reason

# 5. 뉴스 언급량 (Naver API 연동)
class NewsMentionsCondition(BaseCondition):
    def __init__(self, weight=10.0, is_active=True):
        super().__init__("뉴스언급량(Naver)", weight, is_active)
        try:
            from .news_analyzer import fetch_recent_news
            self.fetch_news = fetch_recent_news
        except ImportError:
            self.fetch_news = None

    def evaluate(self, df: pd.DataFrame, ticker: str = "", idx: int = -1, current_score: float = 0.0, fund_data: dict = None) -> tuple[bool, float, str]:
        if not ticker or not self.fetch_news:
            return False, 0.0, "뉴스 검색 불가"
            
        # 최적화: 유망하지 않은 종목(총점 40 미만)은 API 비용/시간 문제로 검색 생략
        if current_score < 40.0:
            return False, 0.0, "점수 미달로 뉴스 검색 생략 (API 최적화)"
            
        try:
            news = self.fetch_news(ticker, display=10)
            passed = bool(len(news) >= 5)
            score = self.weight if passed else 0.0
            reason = f"최근 뉴스 검색 건수 충분({len(news)}건)" if passed else f"뉴스 부족({len(news)}건)"
        except Exception as e:
            passed = False
            score = 0.0
            reason = f"뉴스 크롤링 오류"
            
        return passed, score, reason

# 6. 재무 및 가치/퀄리티 조건
class FundamentalCondition(BaseCondition):
    def __init__(self, weight=20.0, is_active=True):
        super().__init__("재무조건(ROE/PER)", weight, is_active)

    def evaluate(self, df: pd.DataFrame, ticker: str = "", idx: int = -1, current_score: float = 0.0, fund_data: dict = None) -> tuple[bool, float, str]:
        if not fund_data:
            return False, 0.0, "재무 데이터 없음"
            
        per = fund_data.get('PER', 0)
        pbr = fund_data.get('PBR', 0)
        
        # PER, PBR을 통해 ROE 역산 (PBR = Price/BPS, PER = Price/EPS => PBR/PER = EPS/BPS = ROE)
        roe = 0
        if per and pbr and per > 0:
            roe = (pbr / per) * 100
            
        # 평가
        pass_roe = roe > 10.0
        pass_per = 0 < per < 15.0
        
        # 둘 다 만족하면 통과
        passed = bool(pass_roe and pass_per)
        
        # 부분 점수 부여 메커니즘
        score = 0.0
        if pass_roe: score += self.weight * 0.5
        if pass_per: score += self.weight * 0.5
        
        reason_parts = []
        if per > 0: reason_parts.append(f"PER:{per:.1f}")
        if roe > 0: reason_parts.append(f"ROE:{roe:.1f}%")
        reason = " | ".join(reason_parts) if reason_parts else "가치지표 분석불가"
        
        return passed, score, reason

class StockScreener:
    def __init__(self):
        self.conditions = [
            SurgeExcludeCondition(is_active=True), # 너무 오른 종목은 무조건 탈락 (Strict)
            VolumeValueCondition(weight=20.0, is_active=True),
            TrendCondition(weight=20.0, is_active=True),
            TechnicalCondition(weight=20.0, is_active=True),
            ElliottWaveCondition(weight=20.0, is_active=True),
            FundamentalCondition(weight=20.0, is_active=True), # 재무 조건 추가
            NewsMentionsCondition(weight=10.0, is_active=False) 
        ]
        
    def run(self, tickers_data: Dict[str, Dict[str, Any]], target_date_idx: int = -1) -> pd.DataFrame:
        results = []
        for ticker, data in tickers_data.items():
            df = data.get('df')
            fund_data = data.get('fundamentals', {})
            ticker_name = data.get('name', ticker)
            
            if df is None or df.empty:
                continue
                
            total_score = 0.0
            condition_results = {}
            reasons = []
            
            is_valid_stock = True # strict 조건 탈락 여부 플래그
            
            for condition in self.conditions:
                if not condition.is_active:
                    continue
                passed, score, reason = condition.evaluate(df=df, ticker=ticker_name, idx=target_date_idx, current_score=total_score, fund_data=fund_data)
                
                if condition.is_strict and not passed:
                    # 엄격한 필터 조건에서 실패하면 즉시 이 종목을 제외
                    is_valid_stock = False
                    break
                
                condition_results[condition.name] = passed
                total_score += score
                
                if passed and not condition.is_strict: 
                    reasons.append(f"[{condition.name}]")
                
            # strict 필터(예: 급등제외)에서 탈락한 종목은 스킵
            if not is_valid_stock:
                continue
                
            # 총점이 높은 상위 종목만 줄 세우기 (AND 조건은 너무 가혹하므로 유연한 가중치 합산식 복구)
            if total_score > 0:
                res_dict = {
                    "종목명": ticker_name,
                    "티커": ticker,
                    "테마(업종)": data.get('theme', '알 수 없음'),
                    "총점": total_score,
                    "만족조건 (가독성 최적화)": ", ".join(reasons) if reasons else "부분 만족"
                }
                # DataFrame에는 남겨두지만 True/False를 기호로 변경
                res_dict.update({k: ("✅" if v else "❌") for k, v in condition_results.items()})
                results.append(res_dict)
                
        # 점수 순 내림차순 정렬
        result_df = pd.DataFrame(results)
        if not result_df.empty:
            result_df = result_df.sort_values(by="총점", ascending=False).reset_index(drop=True)
            
            base_cols = ["종목명", "티커", "테마(업종)", "총점"]
            cond_cols = [c.name for c in self.conditions if c.is_active and not c.is_strict]
            reason_col = ["만족조건 (가독성 최적화)"]
            
            # 존재하는 컬럼만 선택하도록 안전장치
            valid_cols = [col for col in (base_cols + cond_cols + reason_col) if col in result_df.columns]
            result_df = result_df[valid_cols]
            
        return result_df
