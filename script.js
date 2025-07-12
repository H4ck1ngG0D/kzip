// 要素取得
const uploadInput = document.getElementById('uploadInput');
const fileList = document.getElementById('fileList');
const XOR_KEY = 123;

// ファイル一覧表示
uploadInput.addEventListener('change', () => {
  if (!fileList) return;
  fileList.innerHTML = '';
  for (const file of uploadInput.files) {
    const li = document.createElement('li');
    li.textContent = file.name;
    fileList.appendChild(li);
  }
});

// 暗号化系関数
function toUnicodeEscape(str) {
  return str.split('').map(c =>
    '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0')
  ).join('');
}

function fromUnicodeEscape(str) {
  const regex = /\\u([0-9a-fA-F]{4})/g;
  let result = '';
  let match;
  while ((match = regex.exec(str)) !== null) {
    result += String.fromCharCode(parseInt(match[1], 16));
  }
  return result;
}

function rot13(str) {
  return str.replace(/[A-Za-z]/g, c => {
    const base = c <= 'Z' ? 65 : 97;
    return String.fromCharCode((c.charCodeAt(0) - base + 13) % 26 + base);
  });
}

function caesarShift(str, n) {
  return Array.from(str).map(c => {
    let code = c.charCodeAt(0);
    if (code >= 32 && code <= 126) {
      code = ((code - 32 + n + 95) % 95) + 32;
    }
    return String.fromCharCode(code);
  }).join('');
}

function base64Encode(str) {
  return btoa(unescape(encodeURIComponent(str)));
}

function base64Decode(str) {
  return decodeURIComponent(escape(atob(str)));
}

function xorUint8Array(data, key) {
  return data.map(byte => byte ^ key);
}

function uint8ArrayToString(uint8Array) {
  let result = '';
  const chunkSize = 8192;
  for (let i = 0; i < uint8Array.length; i += chunkSize) {
    const chunk = uint8Array.slice(i, i + chunkSize);
    result += String.fromCharCode(...chunk);
  }
  return result;
}

function stringToUint8Array(str) {
  const arr = new Uint8Array(str.length);
  for (let i = 0; i < str.length; i++) {
    arr[i] = str.charCodeAt(i);
  }
  return arr;
}

// 圧縮＆暗号化
function compressFiles() {
  const files = uploadInput.files;
  if (!files.length) return alert("ファイルを選択してください");

  const zip = new JSZip();
  for (const file of files) zip.file(file.name, file);

  zip.generateAsync({ type: "uint8array" }).then(zipData => {
    const zipStr = uint8ArrayToString(zipData);
    const unicodeEscaped = toUnicodeEscape(zipStr);
    const rot13Str = rot13(unicodeEscaped);
    const caesarStr = caesarShift(rot13Str, 5);
    const base64Str = base64Encode(caesarStr);
    const base64Uint8 = stringToUint8Array(base64Str);
    const encrypted = xorUint8Array(base64Uint8, XOR_KEY);

    const magic = new TextEncoder().encode("KAMICRYPT");
    const finalData = new Uint8Array(magic.length + encrypted.length);
    finalData.set(magic);
    finalData.set(encrypted, magic.length);

    const blob = new Blob([finalData], { type: "application/octet-stream" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "secured.kamichita";
    a.click();
    URL.revokeObjectURL(a.href);
  });
}

// 復号＆.zipとして保存
function decompressFile() {
  const files = uploadInput.files;
  if (!files.length || !files[0].name.endsWith('.kamichita')) {
    return alert(".kamichita ファイルを選択してください");
  }

  const reader = new FileReader();
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

      const blob = new Blob([zipData], { type: "application/zip" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "extracted.zip";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      alert("解凍エラー: " + e.message);
    }
  };
  reader.readAsArrayBuffer(files[0]);
}
