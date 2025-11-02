# api/index.py
# 최종 기능 탑재: 워드프레스 API를 호출하여 RSS 목록을 가져와 분석 (Ver 3.0)

import os
import json
import feedparser
import requests # 워드프레스 호출을 위한 라이브러리
from flask import Flask, request, jsonify
from google import genai
from google.genai.errors import APIError
from concurrent.futures import ThreadPoolExecutor, as_completed

# Flask 앱 초기화
app = Flask(__name__)

# CORS (교차 출처) 문제 해결
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*') 
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# 환경 변수 로드
RIBBONLINE_SECRET_KEY = os.environ.get('RIBBONLINE_SECRET_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
WORDPRESS_SITE_URL = os.environ.get('WORDPRESS_SITE_URL') # 1단계에서 추가한 워드프레스 주소

# --- 헬퍼 함수: RSS 피드 1개를 비동기(병렬)로 가져오는 함수 ---
def fetch_single_feed(url):
    try:
        # User-Agent를 브라우저처럼 위장 (일부 RSS 차단 방지)
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
        feed = feedparser.parse(url, request_headers=headers)
        if feed.entries:
            entry = feed.entries[0] # 각 피드에서 가장 최신 기사 1개만 가져옴
            return f"제목: {entry.title}\n요약: {entry.summary}"
    except Exception as e:
        return f"RSS 피드 파싱 실패: {url}, 오류: {str(e)}"
    return None

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def catch_all(path):
    
    # 1. 보안 인증 (URL 쿼리 파라미터에서 키 수신)
    client_api_key = request.args.get('api_key') 
    if not client_api_key:
        return jsonify({"error": "인증 정보(API Key)가 요청에 포함되지 않았습니다."}), 401
    if client_api_key != RIBBONLINE_SECRET_KEY:
        return jsonify({"error": "API 키가 유효하지 않습니다."}), 403
    
    # 2. 라우팅 경로 확인
    cleaned_path = path.strip().strip('/')
    if cleaned_path == 'collect' or cleaned_path == 'api/collect':
        try:
            # --- 3. 🚀 워드프레스에서 RSS 피드 목록 가져오기 ---
            if not WORDPRESS_SITE_URL:
                return jsonify({"error": "Vercel 환경 변수에 WORDPRESS_SITE_URL이 설정되지 않았습니다."}), 500
            
            wp_api_url = f"{WORDPRESS_SITE_URL}/wp-json/ribbonline/v1/get-feeds"
            
            try:
                response = requests.get(wp_api_url, timeout=10) # 10초 타임아웃
                response.raise_for_status() # 오류 발생 시 예외 처리
                feed_data = response.json()
                
                if feed_data.get('status') != 'success' or not feed_data.get('feeds'):
                    return jsonify({"error": "워드프레스에서 RSS 피드 목록을 가져오는 데 실패했습니다.", "details": feed_data}), 500
                
                feed_urls = feed_data['feeds'] # 100여 개의 RSS 주소 목록

            except requests.RequestException as e:
                return jsonify({"error": f"워드프레스({wp_api_url}) 호출 실패. WP REST API가 작동하는지 확인하세요.", "details": str(e)}), 500
            # --- RSS 목록 가져오기 완료 ---
            
            # --- 4. 100개 피드 병렬 수집 (최적화) ---
            news_summaries = []
            # ThreadPoolExecutor를 사용하여 100개의 피드를 동시에(병렬로) 요청
            with ThreadPoolExecutor(max_workers=20) as executor:
                future_to_url = {executor.submit(fetch_single_feed, url): url for url in feed_urls}
                for future in as_completed(future_to_url):
                    result = future.result()
                    if result:
                        news_summaries.append(result)
            
            if not news_summaries:
                return jsonify({"error": "모든 RSS 피드에서 기사를 수집하는 데 실패했습니다. (네트워크 차단 의심)"}), 500
                
            news_text = "\n---\n".join(news_summaries)
            
            # --- 5. Gemini AI 분석 요청 ---
            if not GEMINI_API_KEY:
                return jsonify({"error": "Gemini API 키가 설정되지 않았습니다."}), 500

            client = genai.Client(api_key=GEMINI_API_KEY)
            
            system_prompt = "당신은 공익 임팩트 지수 분석가입니다. 100여 개의 뉴스 기사 요약본이 제공됩니다. 이 내용들을 종합하여 사회의 공익적 흐름을 평가하고, 다음 JSON 형식에 맞추어 점수와 요약 설명을 제공하세요. 총점은 50점 만점입니다. 점수는 순수한 정수만 포함해야 합니다."
            prompt = (
                f"분석할 뉴스 요약본 묶음:\n---\n{news_text}\n---\n\n"
                "다음 JSON 형식에 맞추어 평가를 완료하세요: {\"total_score\": 0, \"category_scores\": {\"환경\": 0, \"사회\": 0, \"건강\": 0, \"안전\": 0}, \"summary\": \"요약 내용\"}"
            )
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config={'system_instruction': system_prompt, 'response_mime_type': 'application/json'}
            )

            # 6. 최종 결과 반환
            try:
                analysis_result = json.loads(response.text)
                final_response = {
                    "status": "success",
                    "public_index": analysis_result.get('total_score', 0),
                    "category_scores": analysis_result.get('category_scores', {}),
                    "briefing_summary": analysis_result.get('summary', 'AI 요약 생성 실패'),
                    "ai_key_test_gemini": "로드됨",
                    "feed_count": len(feed_urls),
                    "article_count": len(news_summaries)
                }
                return jsonify(final_response), 200, {'Content-Type': 'application/json; charset=utf-8'}

            except json.JSONDecodeError:
                return jsonify({"error": "AI 응답 형식이 잘못되었습니다.", "raw_output": response.text}), 500
            
        except APIError as e:
            return jsonify({"error": "Gemini API 호출 중 오류 발생", "details": str(e)}), 500
        except Exception as e:
            return jsonify({"error": "서버 내부 오류 발생: " + str(e)}), 500

    # 404: 정의되지 않은 API 경로
    return jsonify({"error": f"정의되지 않은 API 경로입니다. Vercel이 수신한 경로(Path): '{path}'"}), 404