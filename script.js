const uploadInput = document.getElementById('uploadInput');
const fileList = document.getElementById('fileList');

uploadInput.addEventListener('change', () => {
  fileList.innerHTML = '';
  for (const file of uploadInput.files) {
    const li = document.createElement('li');
    li.textContent = file.name;
    fileList.appendChild(li);
  }
});

// 文字列 → UTF-16 Unicodeエスケープ（例: \uXXXX形式）
function toUnicodeEscape(str) {
  return str.split('').map(c => {
    return '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0');
  }).join('');
}

// UTF-16 Unicodeエスケープ → 元の文字列に戻す
function fromUnicodeEscape(str) {
  const parts = str.split('\\u');
  let result = parts[0]; // 最初の空白 or 先頭部分

  for (let i = 1; i < parts.length; i++) {
    const code = parts[i].slice(0, 4);
    const rest = parts[i].slice(4);
    result += String.fromCharCode(parseInt(code, 16)) + rest;
  }

  return result;
}

// ROT13変換（アルファベットのみ変換）
function rot13(str) {
  return str.replace(/[A-Za-z]/g, c => {
    const base = c <= 'Z' ? 65 : 97;
    return String.fromCharCode((c.charCodeAt(0) - base + 13) % 26 + base);
  });
}

// Caesarシフト（文字コードを n だけシフト）
function caesarShift(str, n) {
  return Array.from(str).map(c => {
    let code = c.charCodeAt(0);
    // ASCII範囲(32~126)だけシフトしループ
    if (code >= 32 && code <= 126) {
      code = ((code - 32 + n) % 95) + 32;
    }
    return String.fromCharCode(code);
  }).join('');
}

// Base64 encode / decode
function base64Encode(str) {
  return btoa(unescape(encodeURIComponent(str)));
}
function base64Decode(str) {
  return decodeURIComponent(escape(atob(str)));
}

// XOR暗号化（Uint8Arrayに対して）
function xorUint8Array(data, key) {
  return data.map(byte => byte ^ key);
}

// バイナリデータ Uint8Array → 文字列（ISO-8859-1風）
function uint8ArrayToString(uint8Array) {
  return String.fromCharCode(...uint8Array);
}
// 文字列 → Uint8Array
function stringToUint8Array(str) {
  return new Uint8Array([...str].map(c => c.charCodeAt(0)));
}

const XOR_KEY = 123;  // XORキー（0〜255）

// 圧縮→多層暗号化→保存
function compressFiles() {
  const files = uploadInput.files;
  if (!files.length) return alert("ファイルを選択してください");

  const zip = new JSZip();
  for (const file of files) {
    zip.file(file.name, file);
  }

  zip.generateAsync({ type: "uint8array" }).then(zipData => {
    // 1. バイナリを文字列化（ISO-8859-1風）
    const zipStr = uint8ArrayToString(zipData);

    // 2. Unicodeエスケープ
    const unicodeEscaped = toUnicodeEscape(zipStr);

    // 3. ROT13
    const rot13Str = rot13(unicodeEscaped);

    // 4. Caesarシフト +5
    const caesarStr = caesarShift(rot13Str, 5);

    // 5. Base64 encode
    const base64Str = base64Encode(caesarStr);

    // 6. Base64文字列 → Uint8Array
    const base64Uint8 = stringToUint8Array(base64Str);

    // 7. XOR暗号化
    const encrypted = xorUint8Array(base64Uint8, XOR_KEY);

    // 8. マジックバイト付与
    const magic = new TextEncoder().encode("KAMICRYPT");
    const finalData = new Uint8Array(magic.length + encrypted.length);
    finalData.set(magic, 0);
    finalData.set(encrypted, magic.length);

    // 9. ダウンロード
    const blob = new Blob([finalData], { type: "application/octet-stream" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "secured.kamichita";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
  });
}

// 解凍→多層復号
function decompressFile() {
  const files = uploadInput.files;
  if (!files.length || !files[0].name.endsWith('.kamichita')) {
    return alert(".kamichita ファイルを選択してください");
  }

  const reader = new FileReader();

  // 一度だけの onload にする（関数外で定義しない）
  reader.onload = function () {
    try {
      const data = new Uint8Array(reader.result);

      const magic = new TextDecoder().decode(data.slice(0, 9));
      if (magic !== "KAMICRYPT") {
        return alert("正しい .kamichita ファイルではありません");
      }

      const encrypted = data.slice(9);
      const decryptedXOR = xorUint8Array(encrypted, XOR_KEY);
      const base64Str = String.fromCharCode(...decryptedXOR);

      const caesarStr = base64Decode(base64Str);
      const rot13Str = caesarShift(caesarStr, -5);
      const unicodeEscaped = rot13(rot13Str);
      const zipStr = fromUnicodeEscape(unicodeEscaped);
      const zipData = stringToUint8Array(zipStr);

      // ZIPとして保存
      const blob = new Blob([zipData], { type: "application/zip" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "extracted.zip";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      alert("解凍エラー: " + e.message);
    }
  };

  reader.readAsArrayBuffer(files[0]);
}
