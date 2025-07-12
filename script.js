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

// XORキー
const XOR_KEY = 97;

// UTF8エンコード → Base64
function uint8ArrayToBase64(uint8Array) {
  let binary = '';
  for (let i = 0; i < uint8Array.length; i++) {
    binary += String.fromCharCode(uint8Array[i]);
  }
  return btoa(binary);
}

// Base64 → UTF8 Uint8Array
function base64ToUint8Array(base64) {
  const binary = atob(base64);
  const arr = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    arr[i] = binary.charCodeAt(i);
  }
  return arr;
}

// XOR暗号化・復号（対称）
function xorData(uint8Array) {
  return uint8Array.map(byte => byte ^ XOR_KEY);
}

// 圧縮→暗号化→base64→マジックバイト付きでダウンロード
function compressFiles() {
  const files = uploadInput.files;
  if (!files.length) return alert("ファイルを選択してください");

  const zip = new JSZip();
  for (const file of files) {
    zip.file(file.name, file);
  }

  zip.generateAsync({ type: "uint8array" }).then(zipData => {
    // XOR暗号化
    const encrypted = xorData(zipData);

    // base64エンコード
    const base64Str = uint8ArrayToBase64(encrypted);

    // マジックバイト付与 ("KAMI64\n" で識別)
    const finalStr = "KAMI64\n" + base64Str;

    // Blob化してダウンロード
    const blob = new Blob([finalStr], { type: "application/octet-stream" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "secure.kamichita";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
  });
}

// 解凍（独自フォーマット）
function decompressFile() {
  const files = uploadInput.files;
  if (!files.length || !files[0].name.endsWith('.kamichita')) {
    return alert(".kamichita ファイルを選択してください");
  }

  const reader = new FileReader();
  reader.onload = () => {
    const text = reader.result;
    if (!text.startsWith("KAMI64\n")) {
      return alert("正しい .kamichita ファイルではありません");
    }

    const base64Str = text.slice(7); // "KAMI64\n"を除去
    const encrypted = base64ToUint8Array(base64Str);
    const decrypted = xorData(encrypted);

    JSZip.loadAsync(decrypted).then(zip => {
      zip.forEach(async (relativePath, file) => {
        const blob = await file.async("blob");
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = file.name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(a.href);
      });
    }).catch(err => {
      alert("復号または解凍に失敗しました: " + err);
    });
  };
  reader.readAsText(files[0]);
}
