# api/index.py
# 최종 기능 탑재: Cron(백그라운드) + KV(DB)를 사용한 비동기 아키텍처 (Ver 4.0)

import os
import json
import feedparser
import requests
from flask import Flask, request, jsonify
from google import genai
from google.genai.errors import APIError
from concurrent.futures import ThreadPoolExecutor, as_completed
from vercel_kv import kv # 1. Vercel KV(DB) 라이브러리 임포트

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
WORDPRESS_SITE_URL = os.environ.get('WORDPRESS_SITE_URL')
# (DB 관련 키 4개는 vercel-kv 라이브러리가 자동으로 읽어옵니다)

# --- 헬퍼 함수: RSS 피드 1개를 비동기(병렬)로 가져오는 함수 ---
def fetch_single_feed(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        feed = feedparser.parse(url, request_headers=headers)
        if feed.entries:
            entry = feed.entries[0] # 각 피드에서 가장 최신 기사 1개만 가져옴
            return f"제목: {entry.title}\n요약: {entry.summary}"
    except Exception:
        return None
    return None

# --- 헬퍼 함수: AI 분석을 수행하는 메인 로직 ---
def run_ai_analysis():
    # 1. 워드프레스에서 RSS 피드 목록 가져오기
    if not WORDPRESS_SITE_URL:
        return {"error": "WORDPRESS_SITE_URL이 설정되지 않았습니다."}
    
    wp_api_url = f"{WORDPRESS_SITE_URL}/wp-json/ribbonline/v1/get-feeds"
    try:
        response = requests.get(wp_api_url, timeout=10)
        response.raise_for_status()
        feed_data = response.json()
        if feed_data.get('status') != 'success' or not feed_data.get('feeds'):
            return {"error": "워드프레스에서 RSS 피드 목록을 가져오는 데 실패했습니다."}
        feed_urls = feed_data['feeds']
    except requests.RequestException as e:
        return {"error": f"워드프레스({wp_api_url}) 호출 실패.", "details": str(e)}

    # 2. 100개 피드 병렬 수집
    news_summaries = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_url = {executor.submit(fetch_single_feed, url): url for url in feed_urls}
        for future in as_completed(future_to_url):
            result = future.result()
            if result:
                news_summaries.append(result)
    
    if not news_summaries:
        return {"error": "모든 RSS 피드에서 기사를 수집하는 데 실패했습니다."}
        
    news_text = "\n---\n".join(news_summaries)
    
    # 3. Gemini AI 분석 요청
    if not GEMINI_API_KEY:
        return {"error": "Gemini API 키가 설정되지 않았습니다."}

    client = genai.Client(api_key=GEMINI_API_KEY)
    system_prompt = "당신은 공익 임팩트 지수 분석가입니다. 100여 개의 뉴스 기사 요약본이 제공됩니다. 이 내용들을 종합하여 사회의 공익적 흐름을 평가하고, 다음 JSON 형식에 맞추어 점수와 요약 설명을 제공하세요. 총점은 50점 만점입니다. 점수는 순수한 정수만 포함해야 합니다."
    prompt = (
        f"분석할 뉴스 요약본 묶음:\n---\n{news_text}\n---\n\n"
        "다음 JSON 형식에 맞추어 평가를 완료하세요: {\"total_score\": 0, \"category_scores\": {\"환경\": 0, \"사회\": 0, \"건강\": 0, \"안전\": 0}, \"summary\": \"요약 내용\"}"
    )
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={'system_instruction': system_prompt, 'response_mime_type': 'application/json'}
        )
        analysis_result = json.loads(response.text)
        
        # 4. 최종 결과 반환
        final_response = {
            "status": "success",
            "public_index": analysis_result.get('total_score', 0),
            "category_scores": analysis_result.get('category_scores', {}),
            "briefing_summary": analysis_result.get('summary', 'AI 요약 생성 실패'),
            "ai_key_test_gemini": "로드됨",
            "feed_count": len(feed_urls),
            "article_count": len(news_summaries)
        }
        return final_response

    except Exception as e:
        return {"error": "AI 분석 또는 JSON 파싱 중 오류 발생", "details": str(e)}


# --- 🚀 1. 백그라운드 작업 API (Vercel Cron이 1시간마다 호출) ---
@app.route('/api/cron', methods=['GET'])
def cron_job():
    try:
        # AI 분석 실행 (60초 소요될 수 있음)
        analysis_data = run_ai_analysis()
        
        if "error" in analysis_data:
            # 오류 발생 시 DB에 오류 저장
            kv.set("latest_analysis", json.dumps(analysis_data))
        else:
            # 성공 시 DB에 AI 분석 결과 저장
            kv.set("latest_analysis", json.dumps(analysis_data))
            
        return jsonify({"status": "cron_job_completed", "data": analysis_data}), 200
        
    except Exception as e:
        kv.set("latest_analysis", json.dumps({"error": f"Cron job main error: {str(e)}"}))
        return jsonify({"error": f"Cron job main error: {str(e)}"}), 500


# --- 🚀 2. 워드프레스가 호출하는 API (방문자가 보는 페이지) ---
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
            # --- 3. 🚀 DB(Vercel KV)에서 '최신 분석 결과' 읽어오기 ---
            # (AI 분석을 직접 하지 않고, 저장된 결과만 1초 만에 가져옴)
            latest_data_json = kv.get("latest_analysis")
            
            if not latest_data_json:
                # 아직 Cron Job이 실행되기 전 (데이터가 없음)
                return jsonify({
                    "status": "pending",
                    "briefing_summary": "현재 데이터를 수집/분석 중입니다. 잠시 후 새로고침 해주세요."
                }), 200
            
            latest_data = json.loads(latest_data_json)
            
            # DB에 저장된 결과가 오류 메시지일 경우
            if "error" in latest_data:
                 return jsonify({"error": "백그라운드 분석 중 오류 발생", "details": latest_data}), 500

            # DB에서 가져온 최종 결과를 워드프레스로 반환
            return jsonify(latest_data), 200, {'Content-Type': 'application/json; charset=utf-8'}

        except Exception as e:
            return jsonify({"error": f"DB(KV) 조회 중 오류 발생: {str(e)}"}), 500

    # 404: 정의되지 않은 API 경로
    return jsonify({"error": f"정의되지 않은 API 경로입니다. Vercel이 수신한 경로(Path): '{path}'"}), 404