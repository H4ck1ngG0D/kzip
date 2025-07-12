const uploadInput = document.getElementById('uploadInput');
const XOR_KEY = 123;

// 暗号系
function toUnicodeEscape(str) {
  return str.split('').map(c =>
    '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0')
  ).join('');
}
function fromUnicodeEscape(str) {
  return str.replace(/\\u([0-9a-fA-F]{4})/g, (_, g) =>
    String.fromCharCode(parseInt(g, 16))
  );
}
function rot13(str) {
  return str.replace(/[A-Za-z]/g, c => {
    const base = c <= 'Z' ? 65 : 97;
    return String.fromCharCode((c.charCodeAt(0) - base + 13) % 26 + base);
  });
}
function xorUint8Array(data, key) {
  return data.map(byte => byte ^ key);
}
function base64Encode(str) {
  return btoa(unescape(encodeURIComponent(str)));
}
function base64Decode(str) {
  return decodeURIComponent(escape(atob(str)));
}
function uint8ArrayToString(uint8Array) {
  let result = '';
  const chunkSize = 8192;
  for (let i = 0; i < uint8Array.length; i += chunkSize) {
    result += String.fromCharCode(...uint8Array.slice(i, i + chunkSize));
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

// 圧縮＆保存
function compressFiles() {
  const files = uploadInput.files;
  if (!files.length) return alert("ファイルを選択して");

  const zip = new JSZip();
  for (const file of files) zip.file(file.name, file);

  zip.generateAsync({ type: "uint8array" }).then(zipData => {
    const zipStr = uint8ArrayToString(zipData);
    const unicode = toUnicodeEscape(zipStr);
    const roted = rot13(unicode);
    const base64 = base64Encode(roted);
    const encrypted = xorUint8Array(stringToUint8Array(base64), XOR_KEY);

    const blob = new Blob([encrypted], { type: "application/octet-stream" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "encrypted.kamichita";
    a.click();
    URL.revokeObjectURL(a.href);
  });
}

// 解凍
function decompressFile() {
  const files = uploadInput.files;
  if (!files.length || !files[0].name.endsWith(".kamichita")) {
    return alert(".kamichita を選択して");
  }

  const reader = new FileReader();
  reader.onload = () => {
    try {
      const encrypted = new Uint8Array(reader.result);
      const decrypted = xorUint8Array(encrypted, XOR_KEY);
      const base64 = String.fromCharCode(...decrypted);
      const roted = base64Decode(base64);
      const unicode = rot13(roted);
      const zipStr = fromUnicodeEscape(unicode);
      const zipData = stringToUint8Array(zipStr);

      const blob = new Blob([zipData], { type: "application/zip" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "decrypted.zip";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err) {
      alert("エラー: " + err.message);
    }
  };
  reader.readAsArrayBuffer(files[0]);
}
