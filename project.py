import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import yt_dlp
import threading
import os
import re
from urllib.parse import urlparse
from PIL import Image, ImageTk
import requests
from io import BytesIO

# アプリ設定
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class YouTubeDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # ウィンドウ設定
        self.title("📽️ YouTube Downloader")
        self.geometry("700x800")
        self.minsize(600, 700)
        
        # ダウンロードフォルダ
        self.download_folder = os.path.join(os.path.expanduser("~"), "Downloads", "YouTubeDownloader")
        os.makedirs(self.download_folder, exist_ok=True)
        
        # 変数
        self.format_var = tk.StringVar(value="mp4")
        self.is_downloading = False
        
        # UI構築
        self.create_widgets()
        
    def create_widgets(self):
        # メインフレーム
        main_frame = ctk.CTkFrame(self, corner_radius=20, fg_color="white")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # ヘッダー
        header_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        header_frame.pack(pady=(20, 10), padx=20, fill="x")
        
        title_label = ctk.CTkLabel(
            header_frame,
            text="📽️ YouTube Downloader",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#667eea"
        )
        title_label.pack()
        
        subtitle_label = ctk.CTkLabel(
            header_frame,
            text="YouTubeの動画を簡単にダウンロード",
            font=ctk.CTkFont(size=14),
            text_color="#666666"
        )
        subtitle_label.pack(pady=(5, 0))
        
        # URL入力フレーム
        url_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        url_frame.pack(pady=20, padx=20, fill="x")
        
        url_label = ctk.CTkLabel(
            url_frame,
            text="🔗 YouTube URL",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#333333",
            anchor="w"
        )
        url_label.pack(anchor="w", pady=(0, 8))
        
        # URL入力ボックスとクリアボタンのフレーム
        url_input_frame = ctk.CTkFrame(url_frame, fg_color="transparent")
        url_input_frame.pack(fill="x")
        
        self.url_entry = ctk.CTkEntry(
            url_input_frame,
            placeholder_text="https://www.youtube.com/watch?v=...",
            height=50,
            font=ctk.CTkFont(size=14),
            corner_radius=12,
            border_width=2
        )
        self.url_entry.pack(side="left", fill="x", expand=True)
        
        self.clear_btn = ctk.CTkButton(
            url_input_frame,
            text="✕",
            width=40,
            height=40,
            corner_radius=20,
            fg_color="#f0f0f0",
            text_color="#333333",
            hover_color="#e0e0e0",
            command=self.clear_url
        )
        self.clear_btn.pack(side="left", padx=(10, 0))
        
        # フォーマット選択
        format_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        format_frame.pack(pady=20, padx=20, fill="x")
        
        format_label = ctk.CTkLabel(
            format_frame,
            text="📁 フォーマット",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#333333",
            anchor="w"
        )
        format_label.pack(anchor="w", pady=(0, 8))
        
        # ラジオボタンフレーム
        radio_frame = ctk.CTkFrame(format_frame, fg_color="transparent")
        radio_frame.pack(fill="x")
        
        self.mp4_radio = ctk.CTkRadioButton(
            radio_frame,
            text="🎬 MP4 (動画)",
            variable=self.format_var,
            value="mp4",
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=12,
            border_width_checked=8,
            border_width_unchecked=2
        )
        self.mp4_radio.pack(side="left", expand=True, padx=(0, 5))
        
        self.mp3_radio = ctk.CTkRadioButton(
            radio_frame,
            text="🎵 MP3 (音声のみ)",
            variable=self.format_var,
            value="mp3",
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=12,
            border_width_checked=8,
            border_width_unchecked=2
        )
        self.mp3_radio.pack(side="left", expand=True, padx=(5, 0))
        
        # ダウンロードボタン
        self.download_btn = ctk.CTkButton(
            main_frame,
            text="📥 ダウンロード開始",
            height=50,
            font=ctk.CTkFont(size=16, weight="bold"),
            corner_radius=12,
            fg_color="#4CAF50",
            hover_color="#45a049",
            command=self.start_download
        )
        self.download_btn.pack(pady=10, padx=20, fill="x")
        
        # ステータスラベル
        self.status_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=ctk.CTkFont(size=13),
            text_color="#666666",
            wraplength=600
        )
        self.status_label.pack(pady=10, padx=20)
        
        # プログレスバー
        self.progress_bar = ctk.CTkProgressBar(
            main_frame,
            width=600,
            height=15,
            corner_radius=8
        )
        self.progress_bar.pack(pady=10, padx=20, fill="x")
        self.progress_bar.set(0)
        self.progress_bar.pack_forget()  # 初期は非表示
        
        # 結果フレーム
        self.result_frame = ctk.CTkFrame(
            main_frame,
            corner_radius=12,
            fg_color="#f8f9fa"
        )
        self.result_frame.pack(pady=20, padx=20, fill="both", expand=True)
        self.result_frame.pack_forget()  # 初期は非表示
        
        # サムネイル
        self.thumbnail_label = ctk.CTkLabel(
            self.result_frame,
            text="",
            width=300,
            height=200
        )
        self.thumbnail_label.pack(pady=10)
        
        # 動画タイトル
        self.title_label = ctk.CTkLabel(
            self.result_frame,
            text="",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#333333",
            wraplength=600
        )
        self.title_label.pack(pady=5, padx=10)
        
        # フォーマットバッジ
        self.format_badge = ctk.CTkLabel(
            self.result_frame,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="white",
            fg_color="#667eea",
            corner_radius=12,
            width=60,
            height=25
        )
        self.format_badge.pack(pady=5)
        
        # ボタンフレーム
        button_frame = ctk.CTkFrame(self.result_frame, fg_color="transparent")
        button_frame.pack(pady=10, fill="x", padx=10)
        
        self.open_folder_btn = ctk.CTkButton(
            button_frame,
            text="📂 フォルダを開く",
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=8,
            fg_color="#2196F3",
            hover_color="#1976D2",
            command=self.open_download_folder
        )
        self.open_folder_btn.pack(side="left", expand=True, padx=(0, 5), fill="x")
        
        self.open_file_btn = ctk.CTkButton(
            button_frame,
            text="▶️ ファイルを開く",
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=8,
            fg_color="#4CAF50",
            hover_color="#45a049",
            command=self.open_file
        )
        self.open_file_btn.pack(side="left", expand=True, padx=(5, 0), fill="x")
        
        # 特徴フレーム
        features_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        features_frame.pack(pady=20, padx=20, fill="x")
        
        features_label = ctk.CTkLabel(
            features_frame,
            text="✨ 特徴",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#333333"
        )
        features_label.pack(anchor="w", pady=(0, 10))
        
        features_grid = ctk.CTkFrame(features_frame, fg_color="transparent")
        features_grid.pack(fill="x")
        
        features = [
            ("⚡", "高速処理"),
            ("🔒", "安全・安心"),
            ("💾", "ローカル保存"),
            ("⏰", "永久保存")
        ]
        
        for i, (icon, text) in enumerate(features):
            feature_item = ctk.CTkFrame(features_grid, fg_color="transparent")
            feature_item.grid(row=i//2, column=i%2, padx=5, pady=5, sticky="w")
            
            icon_label = ctk.CTkLabel(
                feature_item,
                text=icon,
                font=ctk.CTkFont(size=20)
            )
            icon_label.pack(side="left", padx=(0, 5))
            
            text_label = ctk.CTkLabel(
                feature_item,
                text=text,
                font=ctk.CTkFont(size=13),
                text_color="#666666"
            )
            text_label.pack(side="left")
    
    def clear_url(self):
        """URL入力をクリア"""
        self.url_entry.delete(0, tk.END)
        self.url_entry.focus()
    
    def is_valid_youtube_url(self, url):
        """YouTube URLの妥当性チェック"""
        youtube_patterns = [
            r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/shorts/[\w-]+',
            r'(?:https?://)?youtu\.be/[\w-]+',
            r'(?:https?://)?(?:m\.)?youtube\.com/watch\?v=[\w-]+',
        ]
        return any(re.match(pattern, url) for pattern in youtube_patterns)
    
    def update_status(self, message, color="#666666"):
        """ステータスメッセージを更新"""
        self.status_label.configure(text=message, text_color=color)
    
    def show_progress(self):
        """プログレスバーを表示"""
        self.progress_bar.pack(pady=10, padx=20, fill="x")
        self.progress_bar.set(0)
    
    def hide_progress(self):
        """プログレスバーを非表示"""
        self.progress_bar.pack_forget()
    
    def progress_hook(self, d):
        """yt-dlpのプログレスフック"""
        if d['status'] == 'downloading':
            try:
                percent = d.get('downloaded_bytes', 0) / d.get('total_bytes', 1)
                self.progress_bar.set(percent)
                speed = d.get('speed', 0)
                if speed:
                    speed_mb = speed / (1024 * 1024)
                    self.update_status(f"⏬ ダウンロード中... {percent*100:.1f}% ({speed_mb:.1f} MB/s)")
            except:
                pass
        elif d['status'] == 'finished':
            self.progress_bar.set(1)
            self.update_status("✅ ダウンロード完了！処理中...", "#155724")
    
    def download_thumbnail(self, thumbnail_url):
        """サムネイル画像をダウンロードして表示"""
        try:
            response = requests.get(thumbnail_url, timeout=5)
            img_data = response.content
            img = Image.open(BytesIO(img_data))
            
            # リサイズ
            img.thumbnail((300, 200), Image.Resampling.LANCZOS)
            
            # CTkImageに変換
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(300, 200))
            self.thumbnail_label.configure(image=ctk_img, text="")
            self.thumbnail_label.image = ctk_img  # 参照を保持
        except Exception as e:
            print(f"サムネイル取得エラー: {e}")
            self.thumbnail_label.configure(text="🖼️ サムネイル取得失敗")
    
    def show_result(self, title, format_type, thumbnail_url=None):
        """結果を表示"""
        self.result_frame.pack(pady=20, padx=20, fill="both", expand=True)
        self.title_label.configure(text=title)
        self.format_badge.configure(text=format_type.upper())
        
        if thumbnail_url:
            threading.Thread(target=self.download_thumbnail, args=(thumbnail_url,), daemon=True).start()
    
    def start_download(self):
        """ダウンロード開始"""
        if self.is_downloading:
            messagebox.showwarning("警告", "既にダウンロード中です")
            return
        
        url = self.url_entry.get().strip()
        
        if not url:
            messagebox.showerror("エラー", "URLを入力してください")
            return
        
        if not self.is_valid_youtube_url(url):
            messagebox.showerror("エラー", "有効なYouTube URLを入力してください")
            return
        
        # ダウンロード開始
        self.is_downloading = True
        self.download_btn.configure(state="disabled", text="📥 ダウンロード中...")
        self.result_frame.pack_forget()
        self.show_progress()
        
        format_type = self.format_var.get()
        
        # 別スレッドでダウンロード
        thread = threading.Thread(target=self.download_video, args=(url, format_type), daemon=True)
        thread.start()
    
    def download_video(self, url, format_type):
        """動画をダウンロード"""
        try:
            self.update_status("📥 動画情報を取得中...")
            
            is_audio = format_type == "mp3"
            fmt = "bestaudio/best" if is_audio else "best[ext=mp4]/best"
            
            ydl_opts = {
                'format': fmt,
                'outtmpl': os.path.join(self.download_folder, '%(title)s.%(ext)s'),
                'progress_hooks': [self.progress_hook],
                'quiet': False,
                'no_warnings': False,
            }
            
            # 音声の場合の追加設定
            if is_audio:
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # 動画情報取得
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'Unknown Video')
                thumbnail = info.get('thumbnail')
                
                self.update_status(f"⏬ ダウンロード中: {title[:50]}...")
                
                # ダウンロード実行
                ydl.download([url])
                
                # ファイルパスを保存
                ext = 'mp3' if is_audio else 'mp4'
                self.downloaded_file = os.path.join(self.download_folder, f"{title}.{ext}")
                
                # UIを更新（メインスレッドで実行）
                self.after(0, lambda: self.download_complete(title, format_type, thumbnail))
                
        except Exception as e:
            error_msg = str(e)
            self.after(0, lambda: self.download_error(error_msg))
    
    def download_complete(self, title, format_type, thumbnail):
        """ダウンロード完了時の処理"""
        self.is_downloading = False
        self.download_btn.configure(state="normal", text="📥 ダウンロード開始")
        self.hide_progress()
        self.update_status("✅ ダウンロード完了！", "#155724")
        self.show_result(title, format_type, thumbnail)
        
        messagebox.showinfo("成功", f"ダウンロードが完了しました！\n\n{title}")
    
    def download_error(self, error_msg):
        """ダウンロードエラー時の処理"""
        self.is_downloading = False
        self.download_btn.configure(state="normal", text="📥 ダウンロード開始")
        self.hide_progress()
        self.update_status(f"❌ エラー: {error_msg[:100]}", "#721c24")
        messagebox.showerror("エラー", f"ダウンロードに失敗しました:\n\n{error_msg}")
    
    def open_download_folder(self):
        """ダウンロードフォルダを開く"""
        if os.path.exists(self.download_folder):
            os.startfile(self.download_folder) if os.name == 'nt' else os.system(f'xdg-open "{self.download_folder}"')
        else:
            messagebox.showerror("エラー", "フォルダが見つかりません")
    
    def open_file(self):
        """ダウンロードしたファイルを開く"""
        if hasattr(self, 'downloaded_file') and os.path.exists(self.downloaded_file):
            os.startfile(self.downloaded_file) if os.name == 'nt' else os.system(f'xdg-open "{self.downloaded_file}"')
        else:
            messagebox.showerror("エラー", "ファイルが見つかりません")

if __name__ == "__main__":
    app = YouTubeDownloaderApp()
    app.mainloop()
