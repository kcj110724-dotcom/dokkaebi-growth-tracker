"""도깨비의 세계 성장 기록기 v7: v6 핵심 기록 기능 + GIF 배경.

GIF files are loaded locally, with bounded frame memory and a paced Tk after-loop.
The game is neither controlled nor modified. GIF features do not affect OCR storage.
"""
import math
import os
import queue
import shutil
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, UnidentifiedImageError

from ui_v6 import TrackerV6, HERE, USER_ASSETS, DEFAULT_BG, NAVY, GOLD, MUTED

APP_TITLE = '도깨비의 세계 · 전투력/상세 능력치 기록기 v7'
GIF_FILE = USER_ASSETS / 'user_background.gif'
STATIC_FILE = USER_ASSETS / 'user_background.png'
DEFAULT_FILE = DEFAULT_BG
MAX_GIF_FILE_SIZE = 30 * 1024 * 1024
MAX_GIF_FRAMES = 700
MAX_GIF_PIXELS = 5_000_000
MAX_CACHED_FRAMES = 100
FRAME_THUMB_SIZE = (1080, 640)


def decode_gif_frames(path):
    """Decode composited frames with bounded memory, preserved approximate total timing."""
    path = Path(path)
    if path.stat().st_size > MAX_GIF_FILE_SIZE:
        raise ValueError('GIF 파일이 30MB를 초과해. 더 가벼운 GIF를 사용해 줘.')
    frames = []
    with Image.open(path) as gif:
        if gif.format != 'GIF':
            raise ValueError('올바른 GIF 이미지 파일이 아니야.')
        w, h = gif.size
        if w * h > MAX_GIF_PIXELS:
            raise ValueError('GIF 해상도가 너무 높아. 500만 화소 이하로 줄여 줘.')
        total = getattr(gif, 'n_frames', 1)
        if total > MAX_GIF_FRAMES:
            raise ValueError('프레임이 너무 많은 GIF야. 700프레임 이하를 사용해 줘.')
        if total < 2:
            raise ValueError('움직이는 GIF가 아니야. 정지 이미지를 이용해 줘.')
        stride = max(1, math.ceil(total / MAX_CACHED_FRAMES))
        elapsed = 0
        for i in range(total):
            gif.seek(i)  # Pillow seek presents GIF disposal/composition correctly.
            ms = gif.info.get('duration', 100)
            try: ms = max(20, min(3000, int(ms)))
            except (TypeError, ValueError): ms = 100
            elapsed += ms
            # Combine short-duration frames and downsample long animations.
            if i != total - 1 and ((i + 1) % stride != 0 or elapsed < 85):
                continue
            rgba = gif.convert('RGBA')
            # Transparent pixels get a dark base suitable for the night theme.
            bg = Image.new('RGBA', rgba.size, (14, 21, 36, 255))
            bg.alpha_composite(rgba)
            bg = bg.convert('RGB')
            bg.thumbnail(FRAME_THUMB_SIZE, Image.Resampling.BILINEAR)
            frames.append((bg, max(85, elapsed)))
            elapsed = 0
    if len(frames) < 2:
        raise ValueError('GIF에서 움직이는 프레임을 충분히 찾지 못했어.')
    return frames


class TrackerV7(TrackerV6):
    def __init__(self, root):
        self._gif_frames = []
        self._gif_idx = 0
        self._gif_timer = None
        self._gif_poll_timer = None
        self._gif_events = queue.Queue()
        self._gif_generation = 0
        self._gif_playing = True
        self._gif_loading = False
        self._gif_wall_tick = 0
        self._gif_current_src = None
        super().__init__(root)
        self.root.title(APP_TITLE)
        self.banner.itemconfigure(self.banner_title, text='도깨비의 세계  |  성장 기록기 v7')
        self.banner.itemconfigure(self.banner_sub, text='GIF 배경 · 정확 전투력 · 상세 능력치 24종')
        self._start_gif_loading()
        self._gif_poll_timer = self.root.after(120, self._poll_gif_events)
        self.status.set('v7 준비 완료! PNG/JPG 또는 움직이는 GIF를 배경으로 사용할 수 있어.')

    def _load_theme_images(self):
        # v6 selects PNG by default. Override that only if user GIF exists.
        if GIF_FILE.exists():
            self._theme_image_path = GIF_FILE
        elif STATIC_FILE.exists():
            self._theme_image_path = STATIC_FILE
        else:
            self._theme_image_path = DEFAULT_FILE
        return super()._load_theme_images()

    def _theme_label(self):
        if GIF_FILE.exists():
            return '움직이는 GIF 배경 선택됨 · 재생/일시정지 가능 · 재실행 후에도 유지돼.'
        if STATIC_FILE.exists():
            return '정지 이미지 배경 선택됨 · 프로그램을 다시 실행해도 유지돼.'
        return '기본 판타지 테마 · PNG/JPG/GIF 배경을 자유롭게 골라줘.'

    def make_ui(self):
        super().make_ui()
        # Add animation controls inside the existing themed image section.
        tab_canvas = self.settings_scroller
        inner = tab_canvas.winfo_children()[0]  # inherited scrollable content frame
        cards = inner.winfo_children()
        image_card = cards[0]
        controls = tk.Frame(image_card, bg=NAVY)
        controls.pack(fill='x', padx=17, pady=(0, 12))
        self.gif_play_btn = ttk.Button(controls, text='⏸  GIF 일시정지',
                                       command=self.toggle_gif_playback, style='Secondary.TButton')
        self.gif_play_btn.pack(side='left', padx=(0, 12))
        self._label(controls,'GIF 속도', NAVY, GOLD).pack(side='left', padx=(0, 7))
        self.gif_speed_var = tk.StringVar(value=self.cfg.get('gif_speed', '1.0x'))
        if self.gif_speed_var.get() not in ('0.5x','1.0x','1.5x','2.0x'):
            self.gif_speed_var.set('1.0x')
        speed = ttk.Combobox(controls, textvariable=self.gif_speed_var,
                             values=('0.5x','1.0x','1.5x','2.0x'),state='readonly',width=7)
        speed.pack(side='left', padx=(0, 14))
        speed.bind('<<ComboboxSelected>>', self._speed_changed)
        self.gif_state = tk.StringVar(value='GIF를 선택하면 움직이는 배경이 표시돼.')
        self._label(image_card,'',NAVY,MUTED,textvar=self.gif_state,wrap=950).pack(fill='x',padx=17,pady=(0,10))
        self._gif_playing = bool(self.cfg.get('gif_playing',True))
        self._update_gif_ui()

    def _update_gif_ui(self):
        gif_mode = self._theme_image_path.suffix.lower() == '.gif'
        if hasattr(self,'gif_play_btn'):
            self.gif_play_btn.configure(
                text='⏸  GIF 일시정지' if self._gif_playing else '▶  GIF 재생',
                state='normal' if gif_mode else 'disabled')
        if hasattr(self,'gif_state'):
            if not gif_mode:
                self.gif_state.set('정지 이미지 모드 · 움직임 없이 가볍게 사용해.')
            elif self._gif_loading:
                self.gif_state.set('GIF 프레임 준비 중... 기존 측정 기능은 그대로 사용할 수 있어.')
            elif self._gif_frames:
                state = '재생 중' if self._gif_playing else '일시정지'
                self.gif_state.set(f'GIF {state} · {len(self._gif_frames)}프레임 · 속도 {self.gif_speed_var.get()} · 원본보다 가볍게 최적화')
            else:
                self.gif_state.set('GIF 파일 준비 중 또는 첫 프레임 표시 중')

    def _speed_changed(self, _event=None):
        self.cfg['gif_speed'] = self.gif_speed_var.get()
        self.save_settings()
        self._update_gif_ui()
        if self._gif_frames and self._gif_playing:
            self._stop_gif_timer()
            self._animate_gif()

    def toggle_gif_playback(self):
        if self._theme_image_path.suffix.lower() != '.gif':
            return
        self._gif_playing = not self._gif_playing
        self.cfg['gif_playing'] = self._gif_playing
        self.save_settings()
        self._update_gif_ui()
        self._stop_gif_timer()
        if self._gif_playing and self._gif_frames:
            self._animate_gif()

    def _stop_gif_timer(self):
        if self._gif_timer is not None:
            try:self.root.after_cancel(self._gif_timer)
            except tk.TclError:pass
            self._gif_timer = None

    def _start_gif_loading(self):
        self._gif_generation += 1
        token=self._gif_generation
        self._stop_gif_timer()
        self._gif_frames=[]
        self._gif_idx=0
        self._gif_loading = self._theme_image_path.suffix.lower() == '.gif'
        self._update_gif_ui()
        if not self._gif_loading:
            return
        path=Path(self._theme_image_path)
        def load():
            try:
                frames=decode_gif_frames(path)
                self._gif_events.put(('loaded',token,frames))
            except Exception as ex:
                self._gif_events.put(('error',token,str(ex)))
        threading.Thread(target=load,daemon=True,name='GIFBackgroundLoader').start()

    def _poll_gif_events(self):
        try:
            while True:
                kind,token,result=self._gif_events.get_nowait()
                if token != self._gif_generation:continue  # ignore old file's result
                self._gif_loading=False
                if kind=='error':
                    self._gif_frames=[]
                    self.gif_state.set(f'GIF 애니메이션 사용 불가: {result} · 첫 화면은 유지돼.')
                    self.status.set('GIF 재생에 문제가 있어. 다른 GIF를 선택하거나 정지 이미지를 사용해 줘.')
                else:
                    self._gif_frames=result
                    self._gif_idx=0
                    self._update_gif_ui()
                    if self._gif_playing:self._animate_gif()
        except queue.Empty:
            pass
        try:self._gif_poll_timer=self.root.after(120,self._poll_gif_events)
        except tk.TclError:self._gif_poll_timer=None

    def _animate_gif(self):
        self._gif_timer=None
        if not self._gif_playing or not self._gif_frames:
            return
        frame,ms=self._gif_frames[self._gif_idx]
        self._game_banner_src=frame
        self._wallpaper_src=frame
        self._banner_w=0 # force redraw even if width hasn't changed
        if hasattr(self,'banner') and self.banner.winfo_exists():
            self._render_banner(type('Resize',(),{'width':self.banner.winfo_width()})())
        # Exterior margin uses fewer redraws to reduce GPU/CPU load.
        self._gif_wall_tick += 1
        if self._gif_wall_tick%4==1 and hasattr(self,'wall') and self.wall.winfo_exists():
            self._render_wallpaper()
        self._gif_idx=(self._gif_idx+1)%len(self._gif_frames)
        try:
            speed=float(self.gif_speed_var.get().replace('x',''))
        except ValueError:
            speed=1.0
        self._gif_timer=self.root.after(max(55,round(ms/max(.5,speed))),self._animate_gif)

    def _reload_theme(self):
        self._stop_gif_timer()
        super()._reload_theme()
        self._start_gif_loading()

    def select_theme_image(self):
        selected=filedialog.askopenfilename(
            parent=self.root,title='배경 이미지 또는 움직이는 GIF 선택',
            filetypes=[('이미지와 GIF','*.gif *.png *.jpg *.jpeg *.webp *.bmp'),
                       ('움직이는 GIF','*.gif'),('정지 이미지','*.png *.jpg *.jpeg *.webp *.bmp'),
                       ('모든 파일','*.*')])
        if not selected:return
        selected=Path(selected)
        try:
            if selected.stat().st_size>MAX_GIF_FILE_SIZE:
                raise ValueError('30MB 이하 파일을 선택해 줘. GIF는 용량이 작을수록 부드럽게 재생돼.')
            with Image.open(selected) as check:
                fmt=check.format
                if fmt not in ('GIF','PNG','JPEG','WEBP','BMP'):
                    raise ValueError('지원하지 않는 이미지 형식이야.')
                if check.width * check.height>MAX_GIF_PIXELS:
                    raise ValueError('이미지가 너무 커. 최대 500만 화소 이하를 선택해 줘.')
                if fmt=='GIF':
                    if getattr(check,'n_frames',1)>MAX_GIF_FRAMES:
                        raise ValueError('GIF는 700프레임 이하로 선택해 줘.')
                    target=GIF_FILE
                    tmp=USER_ASSETS/'user_background.tmp.gif'
                    shutil.copyfile(selected,tmp)
                    tmp.replace(target)
                    if STATIC_FILE.exists():STATIC_FILE.unlink()
                else:
                    img=check.convert('RGB')
                    img.thumbnail((2200,1250),Image.Resampling.LANCZOS)
                    target=STATIC_FILE
                    tmp=USER_ASSETS/'user_background.tmp.png'
                    img.save(tmp,optimize=True)
                    tmp.replace(target)
                    if GIF_FILE.exists():GIF_FILE.unlink()
            self._theme_image_path=target
            self._reload_theme()
            self.status.set('움직이는 GIF 배경을 적용했어!' if fmt=='GIF' else '정지 이미지 배경을 적용했어!')
        except (OSError,ValueError,UnidentifiedImageError) as ex:
            messagebox.showerror('배경 적용 실패',str(ex))

    def reset_theme_image(self):
        try:
            for file in (GIF_FILE,STATIC_FILE):
                if file.exists():file.unlink()
            self._theme_image_path=DEFAULT_FILE
            self._reload_theme()
            self.status.set('기본 배경으로 되돌렸어.')
        except OSError as ex:
            messagebox.showerror('배경 초기화 실패',str(ex))

    def save_settings(self):
        if hasattr(self,'gif_speed_var'):
            self.cfg['gif_speed']=self.gif_speed_var.get()
            self.cfg['gif_playing']=self._gif_playing
        return super().save_settings()

    def close(self):
        self._gif_generation+=1
        self._stop_gif_timer()
        if self._gif_poll_timer:
            try:self.root.after_cancel(self._gif_poll_timer)
            except tk.TclError:pass
        super().close()


if __name__ == '__main__':
    root=tk.Tk()
    TrackerV7(root)
    root.mainloop()
