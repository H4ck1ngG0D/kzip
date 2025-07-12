function compressFiles() {
  const input = document.getElementById('uploadInput');
  const files = input.files;
  if (!files.length) return alert("ファイルを選んでください");

  const zip = new JSZip();
  for (const file of files) {
    zip.file(file.name, file);
  }

  zip.generateAsync({ type: "blob" }).then(content => {
    const blob = new Blob([content], { type: "application/octet-stream" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "compressed.kamichita";
    a.click();
  });
}

function decompressFile() {
  const input = document.getElementById('uploadInput');
  const files = input.files;
  if (!files.length || !files[0].name.endsWith('.kamichita')) {
    return alert(".kamichita ファイルを選んでください");
  }

  const reader = new FileReader();
  reader.onload = function(e) {
    JSZip.loadAsync(e.target.result).then(zip => {
      zip.forEach(async (relativePath, file) => {
        const content = await file.async("blob");
        const a = document.createElement("a");
        a.href = URL.createObjectURL(content);
        a.download = file.name;
        a.click();
      });
    });
  };
  reader.readAsArrayBuffer(files[0]);
}
