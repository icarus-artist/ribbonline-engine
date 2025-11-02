# api/index.py
# 최종 기능 탑재, 404 오류 해결을 위한 경로 인식 강화 버전 (Ver 2.7)

import os
import json
import feedparser
from flask import Flask, request, jsonify
from google import genai
from google.genai.errors import APIError

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

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def catch_all(path):
    
    # 1. 보안 인증 (URL 쿼리 파라미터에서 키 수신)
    client_api_key = request.args.get('api_key') 
    
    if not client_api_key: # 쿼리에 없으면 헤더에서 시도
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            client_api_key = auth_header.split(' ')[1]

    if not client_api_key:
        return jsonify({"error": "인증 정보(API Key)가 요청에 포함되지 않았습니다."}), 401

    if client_api_key != RIBBONLINE_SECRET_KEY:
        return jsonify({"error": "API 키가 유효하지 않습니다."}), 403
    
    # --- 핵심 수정: 2. 라우팅 경로 인식을 유연하게 변경 ---
    # 경로 앞뒤의 공백이나 '/' 문자를 모두 제거하고 'collect'와 비교
    cleaned_path = path.strip().strip('/')
    
    if cleaned_path == 'collect':
        # --- (이하 AI 분석 로직은 동일) ---
        try:
            if not GEMINI_API_KEY:
                return jsonify({"error": "Gemini API 키가 설정되지 않았습니다."}), 500

            client = genai.Client(api_key=GEMINI_API_KEY)
            
            rss_url = "https://rss.naver.com/feed/section/105.xml"
            feed = feedparser.parse(rss_url)
            news_summaries = []
            for entry in feed.entries[:3]:
                news_summaries.append(f"제목: {entry.title}\n요약: {entry.summary}")
            news_text = "\n---\n".join(news_summaries)
            
            system_prompt = "당신은 공익 임팩트 지수 분석가입니다. 다음 JSON 형식에 맞추어 점수와 요약 설명을 제공하세요. 총점은 50점 만점입니다. 점수는 순수한 정수만 포함해야 합니다."
            prompt = (
                f"분석할 뉴스:\n---\n{news_text}\n---\n\n"
                "다음 JSON 형식에 맞추어 평가를 완료하세요: {\"total_score\": 0, \"category_scores\": {\"환경\": 0, \"사회\": 0, \"건강\": 0}, \"summary\": \"요약 내용\"}"
            )
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config={'system_instruction': system_prompt, 'response_mime_type': 'application/json'}
            )

            try:
                analysis_result = json.loads(response.text)
                final_response = {
                    "status": "success",
                    "public_index": analysis_result.get('total_score', '점수 없음'),
                    "category_scores": analysis_result.get('category_scores', {}),
                    "briefing_summary": analysis_result.get('summary', '브리핑 요약 없음'),
                    "ai_key_test_gemini": "로드됨"
                }
                return jsonify(final_response), 200, {'Content-Type': 'application/json; charset=utf-8'}

            except json.JSONDecodeError:
                return jsonify({"error": "AI 응답 형식이 잘못되었습니다.", "raw_output": response.text}), 500
            
        except APIError as e:
            return jsonify({"error": "Gemini API 호출 중 오류 발생", "details": str(e)}), 500
        except Exception as e:
            return jsonify({"error": "서버 내부 오류 발생: " + str(e)}), 500

    # 404: 정의되지 않은 API 경로 (디버깅 메시지 추가)
    return jsonify({"error": f"정의되지 않은 API 경로입니다. Vercel이 수신한 경로(Path): '{path}'"}), 404