import google.generativeai as genai
from typing import Dict, Any
from .config import GEMINI_API_KEY

def generate_trading_scenario(
    ticker: str, 
    current_price: float, 
    technical_data: Dict[str, Any], 
    sentiment_data: Dict[str, Any]
) -> str:
    """Gemini API를 활용하여 상승 및 하락 시나리오(대응책 포함)를 생성"""
    if not GEMINI_API_KEY:
        return "⚠️ Gemini API 키가 설정되지 않아 자동 시나리오를 제공할 수 없습니다."
        
    env = technical_data.get("envelope", {})
    wave = technical_data.get("wave", {})
    
    prompt = f"""
당신은 프로 스윙 트레이더이자 금융 분석 에이전트입니다.
'{ticker}' 종목에 대해 다음 데이터를 기반으로 상승장과 하락장 시나리오, 그리고 대응 전략을 제시해주세요.

[최근 분석 데이터]
- 현재가: {current_price:,.0f} (krw)
- Envelope 하단: {env.get('env_lower', 0):,.0f} / 중심: {env.get('env_center', 0):,.0f} / 상단: {env.get('env_upper', 0):,.0f}
- 엘리어트 파동 근사치 평가: {wave.get('wave_status', 'N/A')} (점주: {wave.get('score', 0)}/100)
- 뉴스 감성 점수 (0~100): {sentiment_data.get('score', 50)} ({sentiment_data.get('sentiment', 'Neutral')})
- 최신 요약: {sentiment_data.get('summary', '')}

[요구사항]
아래 형식에 맞춰 마크다운으로 깔끔하게 작성해주세요. 불필요한 서론/결론은 생략합니다.

## 최종 분석 및 진입 타점 가이드
(이 종목이 스윙으로 가져갈만한 이유와 추천 진입 타점을 Envelope 및 파동 점수 등을 활용하여 간략히 서술)

## 상승 시나리오 (Bullish Scenario)
- 주가가 오를 때의 구체적인 움직임 예상과 목표가 (예: 상단 돌파 시 xx원 목표)
- 익절 라인 및 비중 조절 팁

## 하락 시나리오 (Bearish Scenario)
- 주가가 떨어질 때의 하락 지지선 (예: Envelope 하단 등)
- 구체적인 손절 타점 및 대응 전략
"""

    try:
        model = genai.GenerativeModel("models/gemini-1.5-flash")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"시나리오 생성 중 오류 발생: {e}"
