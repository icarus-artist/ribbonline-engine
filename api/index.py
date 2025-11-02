# api/index.py
# 최종 기능 탑재, CORS 허용 및 URL 쿼리 파라미터로 키 수신 버전 (Ver 2.6)

import os
import json
import feedparser
from flask import Flask, request, jsonify
from google import genai
from google.genai.errors import APIError

# Flask 앱 초기화
app = Flask(__name__)

# CORS (교차 출처) 문제 해결: 모든 출처에서의 접근을 허용합니다.
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
    
    # --- 핵심 수정: 1. 헤더 대신 쿼리 파라미터에서 키 추출 ---
    client_api_key = request.args.get('api_key') # URL의 ?api_key=... 에서 키를 읽어옵니다.
    
    if not client_api_key:
        # 쿼리 파라미터에도 없다면 헤더에서도 시도 (안전 장치)
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            client_api_key = auth_header.split(' ')[1]

    if not client_api_key:
        return jsonify({"error": "인증 정보(API Key)가 요청에 포함되지 않았습니다."}), 401

    if client_api_key != RIBBONLINE_SECRET_KEY:
        # 403: API 키 불일치
        return jsonify({"error": "API 키가 유효하지 않습니다."}), 403
    # --- 핵심 수정 끝 ---
    
    # 2. 라우팅: 'collect' 주소 확인
    if path == 'collect':
        try:
            # 3. Gemini 클라이언트 초기화 및 API 호출
            if not GEMINI_API_KEY:
                return jsonify({"error": "Gemini API 키가 설정되지 않았습니다."}), 500

            client = genai.Client(api_key=GEMINI_API_KEY)
            
            # 4. RSS 피드 수집 및 가공 (네이버 IT 뉴스 최신 3개)
            rss_url = "https://rss.naver.com/feed/section/105.xml"
            feed = feedparser.parse(rss_url)
            news_summaries = []
            for entry in feed.entries[:3]:
                news_summaries.append(f"제목: {entry.title}\n요약: {entry.summary}")
            news_text = "\n---\n".join(news_summaries)
            
            # 5. Gemini 프롬프트 정의 및 요청
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

            # 6. 응답 파싱 및 결과 구조화
            try:
                analysis_result = json.loads(response.text)
                
                final_response = {
                    "status": "success",
                    "public_index": analysis_result.get('total_score', '점수 없음'),
                    "category_scores": analysis_result.get('category_scores', {}),
                    "briefing_summary": analysis_result.get('summary', '브리핑 요약 없음'),
                    "ai_key_test_gemini": "로드됨"
                }
                
                # JSON 응답을 명시적으로 UTF-8로 지정하여 워드프레스의 인코딩 오류 방지
                return jsonify(final_response), 200, {'Content-Type': 'application/json; charset=utf-8'}

            except json.JSONDecodeError:
                return jsonify({"error": "AI 응답 형식이 잘못되었습니다.", "raw_output": response.text}), 500
            
        except APIError as e:
            return jsonify({"error": "Gemini API 호출 중 오류 발생", "details": str(e)}), 500
        except Exception as e:
            return jsonify({"error": "서버 내부 오류 발생: " + str(e)}), 500

    # 404: 정의되지 않은 API 경로
    return jsonify({"error": "정의되지 않은 API 경로입니다."}), 404