// cap.js

const API_BASE = "https://2458a847af23-2000.shironekousercontent.paicha.dev";

export function initCaptcha(containerId, options = {}) {
    const container = document.getElementById(containerId);
    if (!container) return console.error("CAPTCHA container not found");

    let currentSession = null;
    let selectedAnswer = null;

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.disabled = true;
    checkbox.id = `${containerId}-checkbox`;

    const label = document.createElement('label');
    label.appendChild(checkbox);
    label.append(" 私はロボットではありません");
    container.appendChild(label);

    const captchaBox = document.createElement('div');
    captchaBox.style.display = 'none';
    container.appendChild(captchaBox);

    const messageBox = document.createElement('div');
    messageBox.style.marginTop = '10px';
    messageBox.style.fontSize = '12px';
    container.appendChild(messageBox);

    fetch(`${API_BASE}/api/captcha/check`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                checkbox.disabled = false;
                checkbox.checked = true;
                captchaBox.style.display = 'block';
                loadCaptcha();
            } else {
                messageBox.textContent = data.message || "ブロックされました";
            }
        })
        .catch(() => {
            messageBox.textContent = "初期チェックに失敗しました";
        });

    function loadCaptcha() {
        fetch(`${API_BASE}/api/captcha`)
            .then(res => res.json())
            .then(data => {
                currentSession = data.session_id;
                selectedAnswer = null;
                captchaBox.innerHTML = '';

                const img = document.createElement('img');
                img.src = 'data:image/png;base64,' + data.image;
                img.alt = 'CAPTCHA';
                img.style.margin = '10px 0';
                captchaBox.appendChild(img);

                const choicesDiv = document.createElement('div');
                data.choices.forEach(choice => {
                    const btn = document.createElement('button');
                    btn.textContent = choice;
                    btn.style.margin = '5px';
                    btn.onclick = () => {
                        selectedAnswer = choice;
                        document.querySelectorAll(`#${containerId} .captcha-choice`).forEach(el => el.style.background = '');
                        btn.style.background = '#007bff';
                        btn.style.color = '#fff';
                        btn.classList.add('captcha-choice');
                    };
                    choicesDiv.appendChild(btn);
                });
                captchaBox.appendChild(choicesDiv);

                const refreshBtn = document.createElement('button');
                refreshBtn.textContent = '更新';
                refreshBtn.onclick = loadCaptcha;
                refreshBtn.style.marginTop = '10px';
                captchaBox.appendChild(refreshBtn);

                const verifyBtn = document.createElement('button');
                verifyBtn.textContent = '認証';
                verifyBtn.onclick = verifyCaptcha;
                verifyBtn.style.marginLeft = '10px';
                captchaBox.appendChild(verifyBtn);
            });
    }

    function verifyCaptcha() {
        if (!selectedAnswer) {
            messageBox.textContent = "選択してください";
            return;
        }

        fetch(`${API_BASE}/api/captcha/verify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: currentSession,
                answer: selectedAnswer
            })
        })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    messageBox.textContent = '✅ 認証成功！';
                    if (options.onSuccess) options.onSuccess(data.token);
                } else {
                    messageBox.textContent = '❌ ' + (data.message || '認証失敗');
                    loadCaptcha();
                }
            })
            .catch(() => {
                messageBox.textContent = "認証エラー";
            });
    }
}
