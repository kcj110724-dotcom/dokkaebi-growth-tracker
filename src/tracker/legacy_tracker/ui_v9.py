"""Game-inspired UI layer for the existing DXcam/OCR tracker.

Never changes OCR, region, hotkeys, game interaction or data files. The capture
and save functionality is still fully provided by TrackerV8.
"""
from __future__ import annotations
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageDraw, ImageFilter, ImageFont
from tracker_v8 import TrackerV8

HERE=Path(__file__).resolve().parent

class TrackerV001(TrackerV8):
    def __init__(self,root):
        self._brand_art = None
        self._small_icon = None
        self._hero_built = False
        super().__init__(root)
        self.root.title('도깨비의 세계 · 측정 센터 v0.0.1')
        self.banner.itemconfigure(self.banner_title,text='성장 기록기  |  측정 센터',font=('맑은 고딕',27,'bold'))
        self.banner.itemconfigure(self.banner_sub,text='전투력 · 상세 능력치 24종 · 자동 측정',font=('맑은 고딕',14,'bold'))
        self.banner.coords(self.banner_title,40,66)
        self.banner.coords(self.banner_sub,42,122)
        self.banner.itemconfigure(self.banner_title,fill='#FFFFFF')
        self.banner.itemconfigure(self.banner_sub,fill='#BDEFFF')
        try:
            im=Image.open(HERE/'assets'/'app_icon.png').convert('RGBA')
            self._small_icon=ImageTk.PhotoImage(im.resize((48,48),Image.Resampling.LANCZOS))
            root.iconphoto(True,self._small_icon)
        except Exception: pass
        try:
            self.tabs.tab(0,text='    ⚔  전투력 · 능력치 측정    ')
            self.tabs.tab(1,text='    ⚙  설정 · 글씨 크기 · 단축키    ')
        except tk.TclError:pass
        self.status.set('준비 완료 · 정확 전투력과 24개 상세 능력치를 기록해 봐.  F5로 기록 확인!')
        root.bind('<F5>',self._manual_refresh,add='+')
        self.banner.after(10,lambda:self._render_banner(type('Resize',(),{'width':self.banner.winfo_width()})()))

    def _manual_refresh(self,_event=None):
        self._refresh_state()
        try:
            self.last_power,self.last_power_approx,self.power_sources=self.load_power()
            self.stat_cache=self.load_stats()
            self.power_label.set(self.describe_power())
            self.update_stats_display()
            self.add_recent('F5 새로고침 · 저장된 전투력/상세 능력치 다시 읽었어.')
            self.status.set('저장된 전투력과 상세 능력치를 다시 불러왔어.')
        except Exception as err:
            self.status.set('새로고침 실패: '+str(err))

    def _render_banner(self,event):
        w=max(1,int(getattr(event,'width',self.banner.winfo_width())))
        if w<100 or abs(w-getattr(self,'_banner_w',0))<5:return
        self._banner_w=w
        art=self._cover_crop(self._game_banner_src,w,182).convert('RGBA')
        # Strong gradient keeps foreground controls readable without discarding artwork.
        overlay=Image.new('RGBA',(w,182),(0,0,0,0))
        g=ImageDraw.Draw(overlay)
        for x in range(w):
            alpha=int(217-70*(x/max(1,w-1)))
            g.line((x,0,x,182),fill=(5,9,36,alpha))
        art.alpha_composite(overlay)
        g=ImageDraw.Draw(art)
        g.rounded_rectangle((18,12,w-18,170),radius=17,outline=(135,124,244,165),width=2)
        g.rounded_rectangle((28,19,34,157),radius=2,fill=(120,113,252,242))
        # Original logo graphic from the approved game-launcher art.
        try:
            src=Image.open(HERE/'assets'/'brand_logo.png').convert('RGBA')
            src.thumbnail((215,143),Image.Resampling.LANCZOS)
            art.alpha_composite(src,(w-src.width-42,max(3,(182-src.height)//2)))
        except Exception:pass
        self._banner_photo=ImageTk.PhotoImage(art.convert('RGB'))
        self.banner.delete('photo')
        self.banner.create_image(0,0,anchor='nw',image=self._banner_photo,tags='photo')
        self.banner.tag_lower('photo')

    def _install_styles(self):
        super()._install_styles()
        self.ttkstyle.configure('TNotebook.Tab',background='#1D2355',foreground='#E5E8FF',padding=(23,13))
        self.ttkstyle.map('TNotebook.Tab',background=[('selected','#4B3CAB'),('active','#303C83')],foreground=[('selected','#FFFFFF')])
        self.ttkstyle.configure('Accent.TButton',background='#684AC4',foreground='#FFFFFF')
        self.ttkstyle.map('Accent.TButton',background=[('active','#8770E1'),('pressed','#4A3597')])
        self.ttkstyle.configure('Primary.TButton',background='#2962A8',foreground='#FFFFFF')
        self.ttkstyle.map('Primary.TButton',background=[('active','#397BD2')])

