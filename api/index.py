# api/index.py
# Vercel에서 Python(Flask)을 실행하는 메인 엔진 파일입니다.

import os
from flask import Flask, request, jsonify

# Flask 앱 초기화
app = Flask(__name__)

# Vercel 환경 변수에서 우리가 설정할 '비밀 키'를 읽어옵니다.
# 이 키는 워드프레스와 백엔드 엔진만 아는 비밀번호입니다.
VERCEL_API_KEY = os.environ.get('VERCEL_API_KEY')

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def catch_all(path):
    # --- 1. 보안 인증: 워드프레스에서 보낸 키가 맞는지 확인 ---
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "인증 헤더가 없습니다."}), 401

    client_api_key = auth_header.split(' ')[1]
    
    if not VERCEL_API_KEY or client_api_key != VERCEL_API_KEY:
        return jsonify({"error": "API 키가 유효하지 않습니다."}), 403

    # --- 2. 라우팅: 'api/collect' 주소로 요청이 왔는지 확인 ---
    # 실제 주소는 https://...vercel.app/api/collect 가 됩니다.
    if path == 'collect':
        try:
            # --- 3. AI 분석 실행 (지금은 테스트 단계) ---
            # TODO: 여기에 RSS 피드 수집 및 AI 분석 로직 추가
            
            # (예시) AI API 키가 잘 로드되었는지 테스트
            ai_key_status = "로드됨" if os.environ.get('GEMINI_API_KEY') else "로드 안됨"

            # 성공 응답 반환
            return jsonify({
                "message": "리본라인 엔진 호출 성공!",
                "status": "ok",
                "requested_path": path,
                "ai_key_test (Gemini)": ai_key_status
            }), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # 정의되지 않은 다른 모든 경로에 대한 404 응답
    return jsonify({"error": "정의되지 않은 API 경로입니다."}), 404

# Vercel은 이 'app' 변수를 찾아 실행합니다.