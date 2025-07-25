from flask import Flask, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont
import random
import string
import hashlib
import time
import json
import io
import base64
from datetime import datetime, timedelta
import re

app = Flask(__name__)

# CAPTCHA設定
CAPTCHA_LENGTH = 5
CAPTCHA_EXPIRE_TIME = 300  # 5分

# セッション管理
captcha_sessions = {}

# VPN/プロキシの疑いがあるIPレンジ（例）
SUSPICIOUS_IP_RANGES = [
    '10.0.0.0/8',
    '172.16.0.0/12',
    '192.168.0.0/16',
    '127.0.0.0/8'
]

# 疑わしいUser-Agent
SUSPICIOUS_USER_AGENTS = [
    'bot', 'spider', 'crawler', 'scraper', 'curl', 'wget',
    'python-requests', 'automated', 'headless'
]

def is_suspicious_ip(ip):
    """IPアドレスが疑わしいかチェック"""
    # 簡単な例 - 実際にはより高度なVPN/プロキシ検出が必要
    private_ranges = ['10.', '172.', '192.168.', '127.']
    return any(ip.startswith(range_) for range_ in private_ranges)

def is_suspicious_user_agent(user_agent):
    """User-Agentが疑わしいかチェック"""
    if not user_agent:
        return True
    
    user_agent_lower = user_agent.lower()
    return any(suspicious in user_agent_lower for suspicious in SUSPICIOUS_USER_AGENTS)

def generate_captcha_text():
    """CAPTCHAテキストを生成"""
    # 読みやすい文字のみ使用（0,O,1,l,I等を除外）
    chars = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
    return ''.join(random.choice(chars) for _ in range(CAPTCHA_LENGTH))

def create_captcha_image(text):
    """CAPTCHA画像を生成"""
    width, height = 200, 80
    image = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(image)
    
    # ノイズを追加
    for _ in range(50):
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.point((x, y), fill='lightgray')
    
    # ランダムな線を追加
    for _ in range(5):
        start = (random.randint(0, width), random.randint(0, height))
        end = (random.randint(0, width), random.randint(0, height))
        draw.line([start, end], fill='gray', width=1)
    
    # テキストを描画
    try:
        # システムフォントを試行
        font_size = 30
        font = ImageFont.load_default()  # デフォルトフォント使用
    except:
        font = None
    
    # 文字を少し歪めて配置
    for i, char in enumerate(text):
        x = 20 + i * 30 + random.randint(-5, 5)
        y = 20 + random.randint(-10, 10)
        
        # 文字の色をランダムに
        color = (
            random.randint(0, 100),
            random.randint(0, 100),
            random.randint(0, 100)
        )
        
        draw.text((x, y), char, fill=color, font=font)
    
    return image

@app.route('/api/captcha/check', methods=['POST'])
def check_client():
    """クライアントの初期チェック"""
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    user_agent = request.headers.get('User-Agent', '')
    
    # IP/UAチェック
    if is_suspicious_ip(client_ip) or is_suspicious_user_agent(user_agent):
        return jsonify({
            'success': False,
            'message': 'アクセスが拒否されました',
            'reason': 'suspicious_client'
        }), 403
    
    return jsonify({
        'success': True,
        'message': 'チェックボックスを有効にできます'
    })

@app.route('/api/captcha', methods=['GET'])
def generate_captcha():
    """CAPTCHA画像とセッションを生成"""
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    user_agent = request.headers.get('User-Agent', '')
    
    # 再度チェック
    if is_suspicious_ip(client_ip) or is_suspicious_user_agent(user_agent):
        return jsonify({'error': 'Access denied'}), 403
    
    # CAPTCHAテキスト生成
    captcha_text = generate_captcha_text()
    
    # セッションID生成
    session_id = hashlib.md5(f"{client_ip}{user_agent}{time.time()}".encode()).hexdigest()
    
    # セッション保存
    captcha_sessions[session_id] = {
        'text': captcha_text,
        'ip': client_ip,
        'user_agent': user_agent,
        'created_at': datetime.now(),
        'verified': False
    }
    
    # 期限切れセッション削除
    cleanup_expired_sessions()
    
    # CAPTCHA画像生成
    image = create_captcha_image(captcha_text)
    
    # 画像をbase64エンコード
    img_buffer = io.BytesIO()
    image.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    # 選択肢生成（正解 + ダミー4つ）
    choices = [captcha_text]
    while len(choices) < 5:
        dummy = generate_captcha_text()
        if dummy not in choices:
            choices.append(dummy)
    
    random.shuffle(choices)
    
    return jsonify({
        'session_id': session_id,
        'image': base64.b64encode(img_buffer.getvalue()).decode(),
        'choices': choices
    })

@app.route('/api/captcha/captcha.png')
def get_captcha_image():
    """CAPTCHA画像を直接取得（画像URL用）"""
    session_id = request.args.get('session')
    if not session_id or session_id not in captcha_sessions:
        # デフォルト画像を返す
        img = Image.new('RGB', (200, 80), color='lightgray')
        draw = ImageDraw.Draw(img)
        draw.text((50, 30), 'Invalid', fill='black')
        
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        return send_file(img_buffer, mimetype='image/png')
    
    session = captcha_sessions[session_id]
    image = create_captcha_image(session['text'])
    
    img_buffer = io.BytesIO()
    image.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    return send_file(img_buffer, mimetype='image/png')

@app.route('/api/captcha/verify', methods=['POST'])
def verify_captcha():
    """CAPTCHA認証"""
    data = request.get_json()
    session_id = data.get('session_id')
    user_answer = data.get('answer')
    
    if not session_id or session_id not in captcha_sessions:
        return jsonify({
            'success': False,
            'message': 'セッションが無効です'
        }), 400
    
    session = captcha_sessions[session_id]
    
    # セッション有効期限チェック
    if datetime.now() - session['created_at'] > timedelta(seconds=CAPTCHA_EXPIRE_TIME):
        del captcha_sessions[session_id]
        return jsonify({
            'success': False,
            'message': 'セッションが期限切れです'
        }), 400
    
    # IP/UAチェック
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    user_agent = request.headers.get('User-Agent', '')
    
    if session['ip'] != client_ip or session['user_agent'] != user_agent:
        return jsonify({
            'success': False,
            'message': '不正なアクセスです'
        }), 403
    
    # 回答チェック
    if user_answer and user_answer.upper() == session['text'].upper():
        session['verified'] = True
        return jsonify({
            'success': True,
            'message': '認証成功！',
            'token': generate_verification_token(session_id)
        })
    else:
        return jsonify({
            'success': False,
            'message': '回答が間違っています'
        })

def generate_verification_token(session_id):
    """認証トークン生成"""
    return hashlib.sha256(f"{session_id}verified{time.time()}".encode()).hexdigest()

def cleanup_expired_sessions():
    """期限切れセッションを削除"""
    now = datetime.now()
    expired_sessions = [
        sid for sid, session in captcha_sessions.items()
        if now - session['created_at'] > timedelta(seconds=CAPTCHA_EXPIRE_TIME)
    ]
    for sid in expired_sessions:
        del captcha_sessions[sid]

@app.route('/demo')
def demo_page():
    """デモページ"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>カスタムCAPTCHA デモ</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }
            .captcha-container { border: 1px solid #ccc; padding: 20px; margin: 20px 0; }
            .captcha-image { margin: 10px 0; }
            .choices { margin: 10px 0; }
            .choice { margin: 5px; padding: 10px; border: 1px solid #ddd; cursor: pointer; }
            .choice:hover { background-color: #f0f0f0; }
            .choice.selected { background-color: #007bff; color: white; }
            .powered-by { font-size: 10px; color: #666; margin-top: 10px; }
            .message { margin: 10px 0; padding: 10px; }
            .success { background-color: #d4edda; color: #155724; }
            .error { background-color: #f8d7da; color: #721c24; }
        </style>
    </head>
    <body>
        <h1>カスタムCAPTCHA デモ</h1>
        
        <div id="step1">
            <h3>ステップ1: 初期チェック</h3>
            <input type="checkbox" id="humanCheck" disabled> 私はロボットではありません
            <button onclick="checkHuman()">チェック開始</button>
        </div>
        
        <div id="step2" style="display:none;">
            <h3>ステップ2: CAPTCHA認証</h3>
            <div class="captcha-container">
                <div>以下の画像の文字を選択してください：</div>
                <div class="captcha-image">
                    <img id="captchaImage" src="" alt="CAPTCHA">
                </div>
                <div class="choices" id="choices"></div>
                <button onclick="refreshCaptcha()">更新</button>
                <button onclick="verifyCaptcha()">認証</button>
                <div class="powered-by">Powered by kamichita</div>
            </div>
        </div>
        
        <div id="messages"></div>
        
        <script>
            let currentSession = null;
            let selectedAnswer = null;
            
            function showMessage(text, type) {
                const messages = document.getElementById('messages');
                messages.innerHTML = `<div class="message ${type}">${text}</div>`;
            }
            
            function checkHuman() {
                fetch('/api/captcha/check', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('humanCheck').disabled = false;
                        document.getElementById('humanCheck').checked = true;
                        document.getElementById('step2').style.display = 'block';
                        loadCaptcha();
                        showMessage('初期チェック完了', 'success');
                    } else {
                        showMessage(data.message, 'error');
                    }
                })
                .catch(error => {
                    showMessage('エラーが発生しました', 'error');
                });
            }
            
            function loadCaptcha() {
                fetch('/api/captcha')
                .then(response => response.json())
                .then(data => {
                    currentSession = data.session_id;
                    document.getElementById('captchaImage').src = 'data:image/png;base64,' + data.image;
                    
                    const choicesDiv = document.getElementById('choices');
                    choicesDiv.innerHTML = '';
                    data.choices.forEach(choice => {
                        const div = document.createElement('div');
                        div.className = 'choice';
                        div.textContent = choice;
                        div.onclick = () => selectChoice(div, choice);
                        choicesDiv.appendChild(div);
                    });
                })
                .catch(error => {
                    showMessage('CAPTCHAの読み込みに失敗しました', 'error');
                });
            }
            
            function selectChoice(element, choice) {
                document.querySelectorAll('.choice').forEach(el => el.classList.remove('selected'));
                element.classList.add('selected');
                selectedAnswer = choice;
            }
            
            function refreshCaptcha() {
                loadCaptcha();
                selectedAnswer = null;
            }
            
            function verifyCaptcha() {
                if (!selectedAnswer) {
                    showMessage('選択肢を選んでください', 'error');
                    return;
                }
                
                fetch('/api/captcha/verify', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        session_id: currentSession,
                        answer: selectedAnswer
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showMessage(data.message + ' トークン: ' + data.token, 'success');
                    } else {
                        showMessage(data.message, 'error');
                        refreshCaptcha();
                    }
                })
                .catch(error => {
                    showMessage('認証に失敗しました', 'error');
                });
            }
        </script>
    </body>
    </html>
    '''

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=2000)
