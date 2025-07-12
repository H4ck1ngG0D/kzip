const uploadInput = document.getElementById('uploadInput');
const fileList = document.getElementById('fileList');

// ファイルリスト表示
uploadInput.addEventListener('change', () => {
  fileList.innerHTML = '';
  for (const file of uploadInput.files) {
    const li = document.createElement('li');
    li.textContent = file.name;
    fileList.appendChild(li);
  }
});

// XORキー（暗号化のキー：好きに変えてOK）
const XOR_KEY = 97; // 文字 'a'

// 圧縮して暗号化 → .kamichitaでダウンロード
function compressFiles() {
  const files = uploadInput.files;
  if (!files.length) return alert("ファイルを選択してください");

  const zip = new JSZip();
  for (const file of files) {
    zip.file(file.name, file);
  }

  zip.generateAsync({ type: "uint8array" }).then(rawData => {
    // XOR暗号化
    const encrypted = rawData.map(byte => byte ^ XOR_KEY);

    // マジックバイト "KAMI" を先頭に付加
    const magic = new TextEncoder().encode("KAMI");
    const finalData = new Uint8Array(magic.length + encrypted.length);
    finalData.set(magic, 0);
    finalData.set(encrypted, magic.length);

    // ダウンロード
    const blob = new Blob([finalData], { type: "application/octet-stream" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "compressed.kamichita";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
  });
}

// .kamichita ファイルを復号・解凍
function decompressFile() {
  const files = uploadInput.files;
  if (!files.length || !files[0].name.endsWith('.kamichita')) {
    return alert(".kamichita ファイルを選んでください");
  }

  const reader = new FileReader();
  reader.onload = () => {
    const data = new Uint8Array(reader.result);

    // マジックバイト確認
    const magic = new TextDecoder().decode(data.slice(0, 4));
    if (magic !== "KAMI") {
      return alert("これは正しい .kamichita ファイルではありません");
    }

    // 復号
    const decrypted = data.slice(4).map(byte => byte ^ XOR_KEY);

    // JSZip で展開
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
  reader.readAsArrayBuffer(files[0]);
}
