import google.generativeai as genai
import requests
import json
import re
from typing import List, Dict, Any
from .config import GEMINI_API_KEY, NAVER_CLIENT_ID, NAVER_CLIENT_SECRET

# Setup Gemini API
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def fetch_recent_news(keyword: str, display: int = 5) -> List[Dict[str, str]]:
    """네이버 뉴스 검색 API를 사용하여 최신 뉴스 반환"""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("Naver API keys not found. Will skip fetching external news.")
        return []
        
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    params = {
        "query": f"{keyword} 주가" if "주가" not in keyword else keyword,
        "display": display,
        "sort": "date" # 최신순
    }
    
    try:
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            data = res.json()
            items = data.get("items", [])
            
            def clean_html(text):
                return re.sub(r'<[^>]+>', '', text).replace('&quot;', '"').replace('&apos;', "'").replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                
            news_list = []
            for item in items:
                news_list.append({
                    "title": clean_html(item["title"]),
                    "description": clean_html(item["description"]),
                    "link": item["link"]
                })
            return news_list
        else:
            print(f"Failed to fetch news. Status: {res.status_code}")
            return []
    except Exception as e:
        print(f"Error fetching news for {keyword}: {e}")
        return []

def analyze_sentiment(keyword: str, news_list: List[Dict[str, str]]) -> Dict[str, Any]:
    """Gemini를 활용하여 뉴스 목록의 전반적인 감성(긍정/부정)을 평가"""
    if not news_list:
        return {"sentiment": "Neutral", "score": 50, "summary": "최근 관련 뉴스 없음"}
        
    if not GEMINI_API_KEY:
        return {"sentiment": "Neutral", "score": 50, "summary": "Gemini API 키가 설정되지 않아 분석 스킵"}
        
    # 뉴스 컨텍스트 만들기
    news_text = "\n".join([f"- {n['title']}: {n['description']}" for n in news_list])
    
    prompt = f"""
다음은 '{keyword}'와(과) 관련된 최근 뉴스 헤드라인과 요약본입니다.
이 뉴스들이 주가나 코인 가격 상승에 긍정적인지(호재), 부정적인지(악재), 혹은 중립적인지 평가해주세요.

뉴스:
{news_text}

아래 JSON 형식으로만 응답해주세요 (절대 마크다운 태그나 다른 설명을 포함하지 마세요):
{{
    "sentiment": "Positive" | "Negative" | "Neutral",
    "score": 0, /* 0부터 100 사이의 숫자. 긍정적일수록 높음 */
    "summary": "1~2문장으로 뉴스가 시사하는 바 요약"
}}
"""
    try:
        # Use simple model available for genai
        # models/gemini-pro or gemini-1.5-flash
        model_name = "models/gemini-1.5-flash"
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        
        res_text = response.text.strip()
        # Clean markdown codeblocks if exist
        if res_text.startswith("```json"):
            res_text = res_text[7:-3].strip()
        elif res_text.startswith("```"):
            res_text = res_text[3:-3].strip()
            
        result = json.loads(res_text)
        return result
    except Exception as e:
        print(f"Error analyzing sentiment for {keyword}: {e}")
        return {"sentiment": "Unknown", "score": 50, "summary": f"분석 중 오류 발생"}
