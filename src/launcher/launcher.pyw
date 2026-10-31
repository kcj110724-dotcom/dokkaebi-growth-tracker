"""Dokkaebi World Growth Tracker — visual launcher · version v0.0.3.

Offline-first desktop launcher; GitHub Release checks and safely verified app
updates are delegated to launcher/update_engine.py. All user records survive
updates in a separate user_data folder. No game memory/automation.
"""
from __future__ import annotations
import io
import webbrowser
import math
import os
import queue
import re
import random
import shutil
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import simpledialog, filedialog, messagebox
from pathlib import Path
from functools import lru_cache
from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageSequence

CODE_ROOT = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('DOKKAEBI_LAUNCHER_ROOT', str(CODE_ROOT))).resolve()
ASSET_ROOT = CODE_ROOT/'assets' if (CODE_ROOT/'assets').is_dir() else ROOT/'assets'
sys.path.insert(0, str(CODE_ROOT/'launcher'))
from update_engine import Store, get_release_zip, version_tuple, atomic_json
from unified_updater import get_available_releases, LauncherManager, is_update, release_order

W,H=1440,810
# Fixed aspect-ratio launcher sizes (16:9), chosen from the settings page.
WINDOW_SIZES = {'small': (1152,648), 'normal': (1280,720), 'large': (1440,810), 'xlarge': (1600,900)}
CTA_SIZES = {
    'compact': (340, 118),
    'default': (405, 140),
    'large': (470, 152),
    'xlarge': (540, 168),
}
NAV=[('home','⌂','홈'),('notes','▤','패치노트'),('versions','◷','버전관리'),('settings','⚙','설정'),('help','?','도움말')]
INK='#F5F5FF'; MUTED='#BDCAE9'; CYAN='#61E8EF'; GOLD='#F3D28F'; PURPLE='#BDA0FF'
DEEP='#080E29'; DARK='#101B3E'
# Preview-only labels; never modify real versions used by updater/rollback.
DISPLAY_VERSION = 'v0.0.3'
VERSION_INLINE_RE = re.compile(r'(?<![A-Za-z0-9])v?\d+\.\d+\.\d+(?![A-Za-z0-9])')
def display_version(real=None):
    return 'v' + str(real).lstrip('v') if real is not None else DISPLAY_VERSION

def version_safe_prose(source):
    return str(source)
FONT_CANDIDATES=(
    'C:/Windows/Fonts/malgun.ttf',
    'C:/Windows/Fonts/malgunbd.ttf',
    '/usr/share/fonts/truetype/nanum/NanumGothic.ttf',
    '/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf',
    '/usr/share/fonts/truetype/nanum/NanumSquareR.ttf',
    'DejaVuSans.ttf',
)
FONT_BOLD_CANDIDATES=('C:/Windows/Fonts/malgunbd.ttf',
    '/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf',
    '/usr/share/fonts/truetype/nanum/NanumSquareB.ttf')


def rgb(x):
    s=x.lstrip('#');return tuple(int(s[i:i+2],16) for i in (0,2,4))

@lru_cache(maxsize=96)
def font(size=16,bold=False):
    paths=(FONT_BOLD_CANDIDATES+FONT_CANDIDATES) if bold else FONT_CANDIDATES
    for item in paths:
        try:return ImageFont.truetype(item,size=size)
        except OSError:pass
    return ImageFont.load_default()


def fit_cover(im,w,h):
    sw,sh=im.size; scale=max(w/sw,h/sh)
    nw,nh=round(sw*scale),round(sh*scale)
    im=im.resize((nw,nh),Image.Resampling.LANCZOS)
    x=(nw-w)//2;y=(nh-h)//2
    return im.crop((x,y,x+w,y+h))


@lru_cache(maxsize=5)
def load_video_frame(path):
    # Bounded frame cache: never preload the entire video into RAM.
    with Image.open(path) as src:
        return src.convert('RGB')


def layer_box(img,xy,fill,outline=None,radius=14,width=1,shadow=0):
    overlay=Image.new('RGBA',img.size,(0,0,0,0));d=ImageDraw.Draw(overlay)
    x1,y1,x2,y2=map(int,xy)
    if shadow:
        sh=Image.new('RGBA',img.size,(0,0,0,0))
        ImageDraw.Draw(sh).rounded_rectangle((x1,y1+6,x2,y2+7),radius=radius,fill=(3,5,22,min(shadow,190)))
        sh=sh.filter(ImageFilter.GaussianBlur(11));img.alpha_composite(sh)
    d.rounded_rectangle((x1,y1,x2,y2),radius=radius,fill=fill,outline=outline,width=width)
    img.alpha_composite(overlay)


def text(im,xy,s,size=16,col=INK,bold=False,anchor=None,spacing=5):
    ImageDraw.Draw(im).multiline_text(xy,str(s),font=font(size,bold),fill=col,
                                     anchor=anchor,spacing=spacing)


def vbar(im,xy,val,color=(95,133,255)):
    x1,y1,x2,y2=xy
    layer_box(im,xy,(17,22,54,215),radius=8)
    layer_box(im,(x1+2,y1+2,x1+max(3,int((x2-x1-4)*max(0,min(1,val)))),y2-2),(*color,255),radius=7)


def paste_resize(im,asset,xy):
    if asset is None:return
    x1,y1,x2,y2=map(int,xy)
    if x2<=x1 or y2<=y1:return
    src=asset.resize((x2-x1,y2-y1),Image.Resampling.LANCZOS)
    im.alpha_composite(src,(x1,y1))

def feather_reference(artwork,w,h):
    """Keep original artwork lettering intact while blending outer edges into video."""
    tile=artwork.resize((w,h),Image.Resampling.LANCZOS).convert('RGBA')
    pix=tile.load()
    for y in range(h):
        yf=min(1.0,(y+1)/7.0,(h-y)/20.0)
        for x in range(w):
            xf=min(1.0,(x+1)/6.0,(w-x)/44.0)
            r,g,b,a=pix[x,y]
            pix[x,y]=(r,g,b,int(a*xf*yf))
    return tile


def transparent_logo(art,w,h):
    """Keep supplied glyph shapes/glow, remove its rectangular dark backing."""
    src=art.resize((w,h),Image.Resampling.LANCZOS).convert('RGBA')
    px=src.load()
    for y in range(h):
        for x in range(w):
            r,g,b,a=px[x,y]
            # Dark navy image backing is knocked out, brighter letter glow remains.
            brightness=max(r,g,b)
            alpha=round(255*max(0,min(1,(brightness-100)/115))**1.4)
            px[x,y]=(r,g,b,min(a,alpha))
    return src


def illustrated_card(img, artwork, rect, label, kind, icon_drawer, active=False):
    """Full-bleed illustration tile with an unobtrusive label overlay."""
    x1,y1,x2,y2=map(int,rect)
    w,h=x2-x1,y2-y1
    if artwork is None or w<=0 or h<=0:return
    tile=fit_cover(artwork,w,h).convert('RGBA')
    mask=Image.new('L',(w,h),0)
    ImageDraw.Draw(mask).rounded_rectangle((0,0,w-1,h-1),radius=12,fill=255)
    # Lower third gradient ensures text stays readable on moving or bright artwork.
    shade=Image.new('RGBA',(w,h),(0,0,0,0))
    d=ImageDraw.Draw(shade)
    for y in range(h):
        yy=y/h
        alpha=int(9+min(1.0,max(0,(yy-0.37)/0.63))*202)
        d.line((0,y,w,y),fill=(6,9,31,alpha))
    tile.alpha_composite(shade)
    tile.putalpha(mask)
    img.alpha_composite(tile,(x1,y1))
    layer_box(img,rect,(0,0,0,0),
              (179,153,255,252) if active else (117,124,218,218),radius=12,width=2)
    icon_drawer(img,kind,x1+23,y2-18,19,'#FFFFFF')
    text(img,(x1+37,y2-27),label,13,'#FFFFFF',True)


def reference_illustration(img, artwork, rect, radius=14):
    """Display supplied reference card as one intact, rounded image."""
    if artwork is None:return
    x1,y1,x2,y2=map(int,rect)
    w,h=x2-x1,y2-y1
    tile=fit_cover(artwork,w,h).convert('RGBA')
    mask=Image.new('L',(w,h),0)
    ImageDraw.Draw(mask).rounded_rectangle((0,0,w-1,h-1),radius=radius,fill=255)
    tile.putalpha(mask)
    img.alpha_composite(tile,(x1,y1))
    layer_box(img,(x1,y1,x2,y2),(0,0,0,0),(91,100,185,207),radius=radius,width=2)


def neon_round(im,rect,main=(183,141,255),width=3,radius=24):
    x1,y1,x2,y2=rect
    for k,alpha in ((17,16),(11,27),(5,58)):
        layer_box(im,(x1-k,y1-k,x2+k,y2+k),(*main,alpha),None,radius+k)
    layer_box(im,rect,(18,23,60,60),(*main,230),radius,width)


class Launcher:
    def __init__(self,root):
        self.root=root
        self.store=Store(ROOT)
        self.launcher_manager=LauncherManager(ROOT)
        self._init_settings()
        self.queue=queue.Queue()
        self.page='home';self.settings_tab='display';self.modal=None;self.hover=None;self.hit={}
        self.settings_scroll={k:0 for k in ('general','display','alerts','data','advanced')}
        self.busy=False;self.proc=None;self.release=None
        self.available_releases={'app':None,'launcher':None}
        self.update_kind=None
        self.latest_status='unknown';self.notes=''
        self.progress=0;self.download_bytes=(0,0)
        self.status='런처 준비 완료. 기존 성장 기록기는 인터넷 없이도 실행할 수 있어.'
        self.needs_render=True;self.base_img=None;self.tk_image=None
        self.bg_item=None;self.bg_photo=None;self.overlay_photo=None
        self.animation_items=[];self.popup_animation_items=[];self.popup_petal_data=[];self.cta_bbox=None;self.cta_item=None;self.blurred=None
        self.after_tick=None
        self.rng=random.Random(716)
        self.sparkles=[self._particle(False) for _ in range(21)]
        self.petals=[self._particle(True) for _ in range(14)]
        self.frame_sources=[];self.gif_idx=0;self.gif_next=0;self.using_video=False;self.video_start=time.monotonic()
        self._update_art=None;self._done_art=None;self._theme_thumbs={};self._logo=None;self._brand_header=None;self._dev_art=None;self._quick_images=[];self._news_art=[];self._loading_art=None;self._cta_art={};self._mascot=None;self._sakura=None
        try:
            with Image.open(ASSET_ROOT/'game_logo_overlay.png') as i:self._logo=i.convert('RGBA').copy()
            with Image.open(ASSET_ROOT/'header_reference.png') as i:self._brand_header=transparent_logo(i.convert('RGBA'),410,88)
            with Image.open(ASSET_ROOT/'developer_message_reference.png') as i:self._dev_art=i.convert('RGBA').copy()
            for n in range(4):
                with Image.open(ASSET_ROOT/f'quick_{n}.jpg') as i:self._quick_images.append(i.convert('RGB').copy())
            for n in range(3):
                with Image.open(ASSET_ROOT/f'news_{n}.png') as i:self._news_art.append(i.convert('RGB').copy())
            for nm in ('run','update'):
                with Image.open(ASSET_ROOT/f'cta_storyboard_{nm}.png') as i:self._cta_art[nm]=i.convert('RGBA').copy()
            with Image.open(ASSET_ROOT/'modal_storyboard_mascot.png') as i:self._mascot=i.convert('RGBA').copy()
            with Image.open(ASSET_ROOT/'popup_sakura.png') as i:self._sakura=i.convert('RGBA').copy()
            with Image.open(ASSET_ROOT/'loading_scenery.png') as i:self._loading_art=i.convert('RGBA').copy()
            with Image.open(ASSET_ROOT/'update_discovery_art.png') as i:
                self._update_art=i.convert('RGBA').copy()
            with Image.open(ASSET_ROOT/'update_success_art.png') as i:
                self._done_art=i.convert('RGBA').copy()
        except Exception:pass
        self._load_background()
        self._make_theme_thumbnails()
        try:self.root.iconbitmap(str(ASSET_ROOT/'dokkaebi_launcher.ico'))
        except Exception:pass
        self.root.title('도깨비의 세계 · 성장 기록기 런처 ' + DISPLAY_VERSION)
        self.root.minsize(1090,620)
        self._apply_window_size(self.store.settings.get('window_size','large'))
        self.root.configure(bg=DEEP)
        self.canvas=tk.Canvas(root,highlightthickness=0,bg=DEEP,cursor='arrow')
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<ButtonRelease-1>',self._click)
        self.canvas.bind('<Motion>',self._motion)
        self.canvas.bind('<B1-Motion>',self._opacity_drag)
        self.canvas.bind('<Leave>',lambda e:self._set_hover(None))
        self.canvas.bind('<Configure>',lambda e:self._mark())
        self.canvas.bind_all('<MouseWheel>',self._mousewheel)
        self.canvas.bind_all('<Button-4>',lambda e:self._mousewheel(e,-1))
        self.canvas.bind_all('<Button-5>',lambda e:self._mousewheel(e,1))
        self.root.bind('<Escape>',self._escape)
        self.root.protocol('WM_DELETE_WINDOW',self._close)
        self._redraw()
        self._tick()
        self.root.after(330,self._start_auto_check)
        self.root.after(650,self.launcher_manager.confirm_healthy)

    def _init_settings(self):
        settings=self.store._settings_cache
        # Keep compatibility, but enable auto-check by default for new installations.
        settings.setdefault('check_on_launch',True)
        settings.setdefault('effects',True)
        settings.setdefault('effect_strength',2)
        settings.setdefault('gif_play',True)
        settings.setdefault('theme','default')
        settings.setdefault('ui_opacity',80)
        settings.setdefault('notify_updates',True)
        settings.setdefault('notify_launch',True)
        settings.setdefault('window_size','large')
        settings.setdefault('cta_size','large')
        self.store._settings_cache=settings
        atomic_json(self.store.settings_file,settings)

    def _apply_window_size(self, size_key):
        """Resize only the launcher window; never alter screenshots or records.

        Clamp to the available monitor size (including taskbar headroom). The
        whole UI scales uniformly from its 1440x810 reference canvas.
        """
        size_key = size_key if size_key in WINDOW_SIZES else 'large'
        requested_w, requested_h = WINDOW_SIZES[size_key]
        avail_w = max(1120, self.root.winfo_screenwidth() - 24)
        avail_h = max(630, self.root.winfo_screenheight() - (72 if sys.platform == 'win32' else 42))
        scale = min(1.0, avail_w/requested_w, avail_h/requested_h)
        width = max(1090, round(requested_w*scale))
        height = max(620, round(requested_h*scale))
        x = max(0,(self.root.winfo_screenwidth()-width)//2)
        y = max(0,(self.root.winfo_screenheight()-height)//2 - 15)
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def _particle(self,petal):
        r=self.rng
        return {'x':r.uniform(0,W),'y':r.uniform(70,H-95),
                'vx':r.uniform(-0.4,-0.08) if petal else r.uniform(-0.06,0.06),
                'vy':r.uniform(0.18,0.49) if petal else r.uniform(-0.08,0.04),
                'r':r.uniform(2,5) if petal else r.uniform(1.2,3.1),
                'phase':r.uniform(0,math.tau),'petal':petal}

    def _load_background(self):
        self.frame_sources=[]
        self.using_video=False
        # User customization wins over the bundled motion background.
        custom=[self.store.data/'assets'/'launcher_background.gif',
                self.store.data/'assets'/'launcher_background.png']
        selected=next((p for p in custom if p.is_file()),None)
        video_dir=ASSET_ROOT/'launcher_video_frames'
        if selected is None and video_dir.is_dir():
            frames=sorted(video_dir.glob('frame_*.jpg'))
            if len(frames)>1:
                self.frame_sources=[str(p) for p in frames]
                self.using_video=True
                self.gif_idx=0
                self.gif_next=time.monotonic()+.11
                self.video_start=time.monotonic()
                return
        if selected is None:
            options=[self.store.data/'assets'/'fixed_background.png',
                     ASSET_ROOT/'original_user_art.gif',ASSET_ROOT/'fixed_background.png']
            selected=next((p for p in options if p.is_file()),None)
        if selected is None:
            self.frame_sources=[Image.new('RGB',(W,H),'#151840')];return
        try:
            with Image.open(selected) as im:
                n=getattr(im,'n_frames',1)
                if n>1:
                    if selected.stat().st_size>30*1024*1024:raise ValueError('GIF 파일이 30MB보다 커.')
                    count=min(50,n)
                    ids=sorted({int(x*(n-1)/max(1,count-1)) for x in range(count)})
                    for idx in ids:
                        im.seek(idx)
                        self.frame_sources.append(fit_cover(im.convert('RGB'),W,H))
                else:self.frame_sources=[fit_cover(im.convert('RGB'),W,H)]
        except Exception:
            self.frame_sources=[Image.new('RGB',(W,H),'#151840')]
        self.gif_idx=0

    def _background(self):
        ref=self.frame_sources[self.gif_idx]
        if isinstance(ref,str):
            im=load_video_frame(ref).copy().convert('RGBA')
            if im.size!=(W,H):im=fit_cover(im,W,H).filter(ImageFilter.UnsharpMask(radius=1.4,percent=65,threshold=2))
        else:
            im=ref.copy().convert('RGBA')
        # A gentle overlay preserves menu contrast without hiding user video.
        ov=Image.new('RGBA',(W,H));d=ImageDraw.Draw(ov)
        for y in range(H):
            alpha=25+int(72*(y/H)**3)+int(35*(1-y/H))
            d.line((0,y,W,y),fill=(5,8,28,alpha))
        im.alpha_composite(ov)
        return im

    def _mark(self):
        self.needs_render=True
        self.root.after_idle(self._redraw)

    def _area(self,name,xy):self.hit[name]=xy

    def _panel(self,im,rect,fill=(8,16,46,220),line=(94,117,196,155),r=16,shadow=0):
        # Opacity affects visual panel fills, not the source artwork or controls.
        if isinstance(fill,tuple) and len(fill)==4 and fill[3]:
            amount=max(45,min(100,int(self.store.settings.get('ui_opacity',80)))) / 80
            fill=(*fill[:3],max(80,min(255,round(fill[3]*amount))))
        layer_box(im,rect,fill,line,r,1,shadow)

    def _main_button(self,im,xy,label,sub,red=False,enabled=True,name='primary'):
        x1,y1,x2,y2=xy
        hovering=self.hover==name
        if hovering:y1-=3;y2-=3
        glow=(255,77,118) if red else (171,136,255)
        for radius,alpha in [(24,13),(17,22),(10,39)]:
            layer_box(im,(x1-radius,y1-radius*.6,x2+radius,y2+radius*.6),(*glow,alpha),None,56,shadow=13)
        art=self._cta_art.get('update' if red else 'run')
        if art is not None:
            paste_resize(im,art,(x1,y1,x2,y2))
        else:
            layer_box(im,(x1,y1,x2,y2),(161,30,70,240) if red else (218,214,255,242),
                      (*glow,250),53,3,shadow=50)
            self._icon(im,'download' if red else 'chart',x1+70,(y1+y2)/2,40,'#FFFFFF' if red else '#3A367B')
            text(im,(x1+112,y1+20),label,26,'white' if red else '#2E235D',True)
        # Decorative name/caption is still authored in the UI; the reference button art supplies the ornament.
        self._area(name,xy)
        self.cta_bbox=(x1,y1,x2,y2)

    def _icon(self,im,kind,x,y,s=28,color='#F3F0FF'):
        # Draw vector glyphs instead of relying on rare Unicode font codepoints.
        d=ImageDraw.Draw(im)
        k=max(2,round(s/11));c=color
        if kind=='home':
            d.line([(x-s*.43,y),(x,y-s*.40),(x+s*.43,y)],fill=c,width=k+1,joint='curve')
            d.rounded_rectangle((x-s*.28,y,x+s*.28,y+s*.39),radius=2,outline=c,width=k)
            d.rectangle((x-s*.085,y+s*.14,x+s*.085,y+s*.39),fill=c)
        elif kind=='notes':
            d.rounded_rectangle((x-s*.29,y-s*.43,x+s*.28,y+s*.40),radius=4,outline=c,width=k)
            for i in range(3):d.line((x-s*.16,y-s*.18+i*s*.19,x+s*.14,y-s*.18+i*s*.19),fill=c,width=k)
        elif kind=='versions' or kind=='rollback':
            d.arc((x-s*.40,y-s*.40,x+s*.40,y+s*.40),40,332,fill=c,width=k+1)
            d.polygon([(x+s*.38,y-s*.1),(x+s*.47,y+s*.13),(x+s*.22,y+s*.11)],fill=c)
            d.line((x,y-s*.25,x,y),fill=c,width=k)
            d.line((x,y,x+s*.18,y+s*.1),fill=c,width=k)
        elif kind=='settings':
            d.ellipse((x-s*.35,y-s*.35,x+s*.35,y+s*.35),outline=c,width=k+1)
            for i in range(8):
                a=i*math.tau/8
                d.line((x+math.cos(a)*s*.31,y+math.sin(a)*s*.31,
                        x+math.cos(a)*s*.47,y+math.sin(a)*s*.47),fill=c,width=k+1)
            d.ellipse((x-s*.12,y-s*.12,x+s*.12,y+s*.12),outline=c,width=k)
        elif kind=='help':
            d.ellipse((x-s*.42,y-s*.42,x+s*.42,y+s*.42),outline=c,width=k+1)
            text(im,(x,y+1),'?',round(s*.7),color,True,anchor='mm')
        elif kind=='external':
            d.rounded_rectangle((x-s*.38,y-s*.32,x+s*.22,y+s*.32),radius=3,outline=c,width=k)
            d.line((x-s*.04,y+s*.10,x+s*.41,y-s*.36),fill=c,width=k+1)
            d.line((x+s*.11,y-s*.37,x+s*.42,y-s*.37,x+s*.42,y-s*.08),fill=c,width=k)
        elif kind=='folder':
            d.rounded_rectangle((x-s*.43,y-s*.19,x+s*.43,y+s*.37),radius=4,outline=c,width=k)
            d.line((x-s*.40,y-s*.20,x-s*.10,y-s*.20,x,y-s*.08,x+s*.38,y-s*.08),fill=c,width=k)
        elif kind=='screenshots':
            d.rounded_rectangle((x-s*.42,y-s*.34,x+s*.42,y+s*.34),radius=4,outline=c,width=k)
            d.ellipse((x+s*.16,y-s*.24,x+s*.27,y-s*.13),fill=c)
            d.line([(x-s*.34,y+s*.23),(x-s*.08,y-s*.04),(x+s*.05,y+s*.08),(x+s*.20,y-s*.02),(x+s*.35,y+s*.21)],fill=c,width=k)
        elif kind=='chart':
            for i,hh in enumerate((.32,.67,.47)):
                l=x-s*.39+i*s*.28
                d.rounded_rectangle((l,y+s*.34-s*hh,l+s*.17,y+s*.34),radius=2,fill=c)
        elif kind=='download':
            d.line((x,y-s*.39,x,y+s*.15),fill=c,width=k+2)
            d.line([(x-s*.17,y-s*.01),(x,y+s*.17),(x+s*.17,y-s*.01)],fill=c,width=k+2)
            d.line((x-s*.34,y+s*.31,x+s*.34,y+s*.31),fill=c,width=k+2)
        else:
            d.ellipse((x-s*.20,y-s*.20,x+s*.20,y+s*.20),fill=c)

    def _nav(self,im):
        # Ref: approved storyboard 01/02/06. The controls sit above the image, no left rail.
        # Reuse the exact header artwork provided by the user.
        if self._brand_header is not None:
            im.alpha_composite(self._brand_header,(12,5))
        else:
            self._panel(im,(12,8,421,82),(8,14,45,193),(64,74,143,100),12)
            text(im,(26,15),'도깨비의 세계',25,'#F1EFFF',True)
            text(im,(221,20),'성장 기록기 런처 ›',18,'#FBF9FF',True)
            text(im,(223,52),'DOKKAEBI WORLD GROWTH TRACKER',10,'#B8C6E9')
        nav_x=[478,585,692,799,906]
        for (key,ico,label),x in zip(NAV,nav_x):
            sel=self.page==key
            rect=(x,8,x+96,82)
            if sel:self._panel(im,rect,(61,45,163,204),(143,122,255,224),14)
            elif self.hover=='nav:'+key:self._panel(im,rect,(47,40,119,177),(126,132,225,170),13)
            self._icon(im,key,x+48,31,25,'#FFFFFF' if sel else '#C8D2F3')
            text(im,(x+48,54),label,14,'#FFFFFF' if sel else '#D4D8F3',bold=sel,anchor='mt')
            self._area('nav:'+key,rect)
        self._panel(im,(1169,27,1415,74),(10,17,49,227),
                    (141,86,143,200) if self.latest_status=='new' else (75,109,179,168),27)
        status=self.latest_status
        if status=='new':
            text(im,(1195,40),'● '+('런처' if self.update_kind=='launcher' else '기록기')+' 업데이트',15,'#FF849C',True)
            text(im,(1398,42),display_version(self.release['version']),14,'#FFDCE7',True,anchor='ra')
        elif status=='latest':
            text(im,(1195,40),'● 최신 버전',15,'#66F0BA',True)
            text(im,(1398,42),display_version(self.store.state['current']),14,'#EFF1FF',True,anchor='ra')
        elif status=='checking':text(im,(1195,40),'◌ 업데이트 확인 중',14,'#CADBFF',True)
        elif status=='error':text(im,(1195,40),'● 확인 실패',14,'#FFB4C4',True)
        else:text(im,(1195,40),'◇ 업데이트 미연결',14,'#D0D5F3',True)

    def _home_logo(self,im):
        # The user's animated MP4 already includes the central official logo.
        # Don't add a second extracted logo on top of that one.
        return



    def _cta_rect(self):
        """Return the approved home CTA placement, right-aligned under latest news.

        Width/height are user-configurable from settings, but the button always
        stays visually anchored below the latest-news card and above the bottom
        quick-menu strip.
        """
        key = self.store.settings.get('cta_size','large')
        w,h = CTA_SIZES.get(key, CTA_SIZES['large'])
        x2 = 1415
        x1 = x2 - w
        # keep the button in the same neighborhood even when size changes
        base_y = 473
        if h >= 160:
            y1 = 458
        elif h >= 148:
            y1 = 466
        elif h <= 122:
            y1 = 482
        else:
            y1 = base_y
        y2 = y1 + h
        return (x1,y1,x2,y2)

    def _home(self,im):
        self._home_logo(im)
        # Keep the moving video scene and figures unobscured through the middle of the window.
        # Approved-home layout: news artwork right, primary CTA directly below;
        # bottom is version / quick menu / developer art. No 'game launch' button.
        self._panel(im,(1012,118,1416,449),(8,13,43,231),(139,111,206,222),18,shadow=45)
        text(im,(1033,134),'최신 소식',21,'#FFFFFF',True)
        text(im,(1393,138),'더보기 ›',13,'#D6CEFF',anchor='ra')
        self._area('news',(1012,118,1416,449))
        news=self._news_rows()
        for i,(tag,label,color) in enumerate(news[:3]):
            y=171+i*90
            self._panel(im,(1025,y,1405,y+84),(14,21,54,234),(57,64,121,133),11)
            if i<len(self._news_art):
                artwork=fit_cover(self._news_art[i],108,72).convert('RGBA')
                mask=Image.new('L',(108,72),0)
                ImageDraw.Draw(mask).rounded_rectangle((0,0,107,71),radius=9,fill=255)
                artwork.putalpha(mask)
                im.alpha_composite(artwork,(1031,y+6))
            self._panel(im,(1148,y+9,1203,y+30),(*rgb(color),244),None,6)
            text(im,(1175,y+12),tag,11,'#FFFFFF',True,anchor='mt')
            text(im,(1211,y+10),label[:16],14,'#FFFFFF',True)
            if i==0:
                text(im,(1210,y+40),'상세 내용은 패치노트에서 확인',11,'#BED1EF')
            else:
                text(im,(1210,y+40),'개인 정보는 외부 전송 안 함',11,'#AFC4E8')
        cta_rect = self._cta_rect()
        if self.latest_status=='new':
            self._main_button(im,cta_rect,'업데이트','새 버전으로 업데이트해 줘.',True)
            text(im,(1394,cta_rect[3]+16),'기존 버전 실행 ›',12,'#F8E0ED',True,anchor='ra')
            self._area('oldapp',(1246,cta_rect[3]+9,1418,cta_rect[3]+40))
        else:
            self._main_button(im,cta_rect,'성장 기록기 실행','도깨비의 세계 성장 기록',False)
        # Wide illustrated cards: fill the entire tile instead of shrinking images to a 38px strip.
        self._panel(im,(20,674,284,800),(7,14,42,237),(92,107,180,169),17)
        text(im,(42,685),'성장 기록기 버전',14,'#86E3E5',True)
        text(im,(43,713),display_version(self.store.state['current']),26,'#FFFFFF',True)
        text(im,(165,737),'런처 '+display_version(self.launcher_manager.active()),12,'#D3C6FF')
        badge='● 업데이트 필요' if self.latest_status=='new' else '● 최신 버전' if self.latest_status=='latest' else '● 설치된 버전 실행 가능'
        text(im,(43,771),badge,12,'#FF8CA6' if self.latest_status=='new' else '#75EFC0')

        self._panel(im,(296,674,984,800),(8,17,47,237),(100,111,184,160),17)
        text(im,(317,682),'빠른 메뉴',15,'#E5C9FF',True)
        quick=[('quick:data','기록 폴더'),('quick:shots','스크린샷'),('quick:kkaebigg','깨비지지'),('quick:rollback','이전 버전 복구')]
        icons=('folder','screenshots','external','rollback')
        for i,(key,lab) in enumerate(quick):
            x=312+i*166
            rect=(x,712,x+157,792)
            if i<len(self._quick_images):
                illustrated_card(im,self._quick_images[i],rect,lab,icons[i],self._icon,self.hover==key)
            else:
                self._panel(im,rect,(24,34,79,233),(122,108,206,225),12)
                self._icon(im,icons[i],x+25,750,24,'#FFFFFF')
                text(im,(x+45,755),lab,13,'#FFFFFF',True)
            self._area(key,rect)

        # Entire user-supplied illustration fills developer's message card; no duplicate labels.
        if self._dev_art is not None:
            reference_illustration(im,self._dev_art,(995,674,1418,800),15)
        else:
            self._panel(im,(995,674,1418,800),(8,17,47,235),(100,111,184,160),17)
            text(im,(1012,685),'개발자 한마디',16,'#E8C8FF',True)
            text(im,(1012,729),'“도깨비의 세계에서의 성장을',14,'#ECEAFF')
            text(im,(1012,754),'언제든 다시 확인할 수 있도록!”',14,'#E2DAFA')

    def _news_rows(self):
        if self.release:
            return [('패치',display_version(self.release['version'])+' 배포 정보','#AC4E98'),
                    ('안내','새 버전의 변경사항 확인', '#257C9F'),
                    ('기록','CSV · 배경 · 단축키 보존', '#1F9F91'),
                    ('복구','필요할 때 이전 버전으로', '#754FC2'),
                    ('기타','패치노트에서 자세히 보기', '#515D95')]
        return [('안내','현재 설치된 성장 기록기', '#AC4E98'),
                ('기능','정확 전투력 기록', '#257C9F'),
                ('기능','상세 능력치 24개 추적', '#1F9F91'),
                ('안전','데이터 백업과 롤백', '#754FC2'),
                ('설정','GitHub 저장소 연결하기', '#515D95')]

    def _page_close(self, im):
        # Browser-style close for top-navigation pages. Returns to the home
        # dashboard; this does not close the launcher or alter recording data.
        x1,y1,x2,y2=(1168,146,1220,197)
        self._panel(im,(x1,y1,x2,y2),
                    (76,42,116,235) if self.hover=='page:close' else (26,39,84,224),
                    (202,159,255,241),12)
        d=ImageDraw.Draw(im)
        cx=(x1+x2)//2;cy=(y1+y2)//2
        d.line((cx-9,cy-9,cx+9,cy+9),fill=(255,246,255),width=3)
        d.line((cx+9,cy-9,cx-9,cy+9),fill=(255,246,255),width=3)
        self._area('page:close',(x1,y1,x2,y2))

    def _panel_page(self,im,title,subtitle):
        self._panel(im,(185,124,1260,725),(6,12,39,231),(94,104,177,186),22,shadow=80)
        text(im,(223,157),title,30,INK,True)
        text(im,(224,210),subtitle,16,MUTED)
        layer_box(im,(215,249,1230,251),(99,88,158,180),radius=1)
        self._page_close(im)

    def _notes(self,im):
        self._panel_page(im,'패치노트','공식 GitHub Releases의 변경 사항을 확인해. 실제 공개된 내용만 표시해.')
        self._panel(im,(221,275,495,669),(17,27,69,215),(79,90,156,143),13)
        versions=sorted(self._known_versions(),key=lambda v:release_order('app',v),reverse=True)
        for i,v in enumerate(versions[:6]):
            y=296+i*59
            self._panel(im,(238,y,477,y+47),(72,53,151,206) if i==0 else (30,42,88,178),None,9)
            text(im,(252,y+9),display_version(v),19,INK,True)
            text(im,(418,y+13),'설치됨' if v==self.store.state['current'] else '보관',12,CYAN,anchor='ra')
        self._panel(im,(516,275,1224,669),(17,27,69,215),(79,90,156,143),13)
        text(im,(548,300),'새 버전 변경 사항',22,INK,True)
        text(im,(550,343),display_version(self.release['version']) if self.release else 'GitHub 연결 전',17,'#D9C3FF',True)
        notes=self.notes if self.release else ('GitHub 저장소를 연결하면 게시된 패치노트가 여기에 표시돼.\n\n'
              '기본 탑재 기록기 기능:\n· 전체화면 DXcam 캡처 진단\n· 정확한 전투력 기록 및 상세 능력치 24개\n· GIF 배경, 글씨 크기와 단축키 변경')
        for i,line in enumerate(notes.splitlines()[:11]):
            text(im,(550,388+i*24),version_safe_prose(line)[:72],15,'#D4DBF4')
        self._button(im,'다시 확인','check',(955,632,1201,676),accent='violet')

    def _known_versions(self):
        return self.store.known_versions()

    def _versions(self,im):
        self._panel_page(im,'버전 관리 · 복구','업데이트는 새로운 폴더에 설치되며, 기존 버전과 기록은 유지돼.')
        versions=sorted(self._known_versions(),key=lambda v:release_order('app',v),reverse=True)
        for i,v in enumerate(versions[:6]):
            y=285+i*63
            self._panel(im,(226,y,1219,y+54),(20,33,77,215),(64,81,147,162),11)
            text(im,(248,y+12),display_version(v),18,INK,True)
            current=(v==self.store.state['current'])
            text(im,(456,y+15),'●  현재 버전' if current else '이전 설치 버전',14,CYAN if current else MUTED)
            if not current:
                self._button(im,'이 버전으로 복구','rollback:'+v,(953,y+7,1202,y+46),accent='violet')
        self._button(im,'기록 백업 만들기','backup',(231,671,470,716),accent='violet')
        self._button(im,'기존 기록 가져오기','import',(482,671,749,716),accent='violet')
        self._button(im,'기록 폴더 열기','data',(766,671,998,716),accent='violet')

    def _button(self,im,label,key,rect,accent='violet'):
        fg=(225,232,255,255) if accent!='red' else (255,224,233,255)
        bg=(48,38,113,226) if accent=='violet' else (35,81,101,236) if accent=='cyan' else (145,34,73,230)
        self._panel(im,rect,bg,(110,106,220,210),12)
        x1,y1,x2,y2=rect
        text(im,((x1+x2)/2,(y1+y2)/2),label,15,fg,True,anchor='mm')
        self._area(key,rect)

    def _make_theme_thumbnails(self):
        src=ASSET_ROOT/'fixed_background.png'
        try:
            with Image.open(src) as img:base=fit_cover(img.convert('RGB'),184,96)
        except Exception:base=Image.new('RGB',(184,96),'#26376D')
        self._theme_thumbs={
            'default':base.convert('RGBA'),
            'dark':ImageEnhance.Brightness(base).enhance(0.36).convert('RGBA'),
            'light':ImageEnhance.Brightness(ImageEnhance.Color(base).enhance(0.66)).enhance(1.45).convert('RGBA'),
        }

    def _setting_item(self,im,label,desc,y,key,value=None,selected=False):
        rect=(246,y,452,y+61)
        self._panel(im,rect,(35,65,151,223) if selected else (13,26,64,224),
                    (81,176,255,238) if selected else (86,106,180,146),12)
        self._icon(im,'settings' if key=='general' else 'home' if key=='display' else 'notes' if key=='alerts' else 'folder' if key=='data' else 'versions',270,y+27,20)
        text(im,(296,y+18),label,17,'#FFFFFF' if selected else '#D0D6FC',True)
        self._area('settings-tab:'+key,rect)

    def _setting_toggle(self,im, label, desc, y, key, enabled):
        text(im,(548,y),label,19,'#EDF4FF',True)
        text(im,(549,y+29),desc,13,'#AEBFE6')
        rect=(1061,y,1147,y+36)
        self._panel(im,rect,(66,100,224,255) if enabled else (38,53,99,235),
                    (108,172,255,230) if enabled else (90,108,173,195),18)
        cx=1127 if enabled else 1081
        ImageDraw.Draw(im).ellipse((cx-12,y+6,cx+12,y+30),fill='#FFFFFF')
        self._area('setting:'+key, (532,y-6,1158,y+49))

    def _settings(self,im):
        # Designed after the user-approved 2026-10-28 settings reference.
        # The content area clips and scrolls so extra options never spill outside.
        self._panel(im,(198,125,1246,725),(7,15,48,245),(108,107,219,215),22,shadow=54)
        self._page_close(im)
        self._icon(im,'settings',260,178,42,'#A3D7FF')
        text(im,(302,148),'설정',31,'#F2F5FF',True)
        text(im,(303,200),'성장 기록기 런처의 환경을 설정할 수 있어.',16,'#C2CFF5')
        self._panel(im,(225,248,1216,696),(7,14,41,226),(105,127,211,185),17)
        ImageDraw.Draw(im).line((465,254,465,689),fill=(90,111,172,190),width=2)
        items=[('general','일반 설정'),('display','화면 설정'),('alerts','알림 설정'),('data','데이터 관리'),('advanced','고급 설정')]
        for i,(key,label) in enumerate(items):
            self._setting_item(im,label,'',286+i*77,key,selected=self.settings_tab==key)

        tab=self.settings_tab
        vx1,vy1,vx2,vy2=487,264,1182,688
        view_w=view_h=0
        view_w=vx2-vx1; view_h=vy2-vy1
        content_h_map={'general':362,'display':548,'alerts':334,'data':360,'advanced':384}
        content_h=max(view_h,content_h_map.get(tab,view_h))
        max_scroll=max(0,content_h-view_h)
        scroll=max(0,min(int(self.settings_scroll.get(tab,0)),max_scroll))
        self.settings_scroll[tab]=scroll

        layer=Image.new('RGBA',(view_w,content_h),(0,0,0,0))
        draw=ImageDraw.Draw(layer)

        def loc_rect(rect):
            x1,y1,x2,y2=rect
            return (x1-vx1,y1-vy1,x2-vx1,y2-vy1)
        def c_panel(rect,fill=(8,16,46,220),line=(94,117,196,155),r=16,shadow=0):
            self._panel(layer,loc_rect(rect),fill,line,r,shadow)
        def c_text(pt,s,size=16,col=INK,bold=False,anchor=None,spacing=5):
            text(layer,(pt[0]-vx1,pt[1]-vy1),s,size,col,bold,anchor,spacing)
        def c_line(coords,fill,width=1):
            coords=[coords[0]-vx1,coords[1]-vy1,coords[2]-vx1,coords[3]-vy1]
            draw.line(coords,fill=fill,width=width)
        def c_box(rect,fill,outline=None,radius=14,width=1,shadow=0):
            layer_box(layer,loc_rect(rect),fill,outline,radius,width,shadow)
        def c_paste(asset,rect):
            if asset is None:return
            paste_resize(layer,asset,loc_rect(rect))
        def c_area(name,rect):
            x1,y1,x2,y2=rect
            sy1=y1-scroll; sy2=y2-scroll
            ax1=max(vx1,x1); ay1=max(vy1,sy1); ax2=min(vx2,x2); ay2=min(vy2,sy2)
            if ax1<ax2 and ay1<ay2:self._area(name,(ax1,ay1,ax2,ay2))
        def c_button(label,key,rect,accent='violet'):
            palette={'violet':((56,46,128,240),(138,118,255,236)),'cyan':((43,91,115,240),(112,214,255,236))}
            fill,line=palette.get(accent,palette['violet'])
            c_panel(rect,fill,line,12,shadow=10)
            x1,y1,x2,y2=rect
            c_text(((x1+x2)/2,(y1+y2)/2),label,15,'#FFFFFF',True,anchor='mm')
            c_area(key,rect)
        def c_toggle(label,desc,y,key,enabled):
            c_text((548,y),label,19,'#EDF4FF',True)
            c_text((549,y+29),desc,13,'#AEBFE6')
            rect=(1061,y,1147,y+36)
            c_panel(rect,(66,100,224,255) if enabled else (38,53,99,235),
                    (108,172,255,230) if enabled else (90,108,173,195),18)
            cx=1127 if enabled else 1081
            ImageDraw.Draw(layer).ellipse((cx-vx1-12,y-vy1+6,cx-vx1+12,y-vy1+30),fill='#FFFFFF')
            c_area('setting:'+key,(532,y-6,1158,y+49))

        if tab=='display':
            c_text((510,274),'화면 설정',23,'#FFFFFF',True)
            c_text((510,303),'창 크기·실행 버튼 크기·테마·애니메이션·UI 투명도를 조절해.',13,'#B1C6F2')
            c_text((510,329),'런처 창 크기',17,'#E6EEFF',True)
            size_labels=[('small','작게'),('normal','보통'),('large','크게'),('xlarge','아주 크게')]
            current_size=self.store.settings.get('window_size','large')
            for i,(key,label) in enumerate(size_labels):
                x=509+i*168
                rect=(x,354,x+156,391)
                selected=current_size==key
                c_panel(rect,(47,76,174,240) if selected else (20,31,80,230),
                        (107,200,255,244) if selected else (83,105,175,194),10)
                c_text((x+78,360),label,14,'#FFFFFF' if selected else '#C9D7F9',selected,anchor='mt')
                c_area('setting:window_size:'+key,rect)
            c_text((510,406),'성장 기록기 실행 버튼 크기',17,'#E6EEFF',True)
            cta_labels=[('compact','작게'),('default','기본'),('large','크게'),('xlarge','아주 크게')]
            current_cta=self.store.settings.get('cta_size','large')
            for i,(key,label) in enumerate(cta_labels):
                x=509+i*168
                rect=(x,431,x+156,468)
                selected=current_cta==key
                c_panel(rect,(47,76,174,240) if selected else (20,31,80,230),
                        (255,179,235,244) if selected else (83,105,175,194),10)
                c_text((x+78,437),label,14,'#FFFFFF' if selected else '#C9D7F9',selected,anchor='mt')
                c_area('setting:cta_size:'+key,rect)
            c_text((510,486),'런처 테마',17,'#E6EEFF',True)
            themes=[('default','기본 테마'),('dark','어두운 테마'),('light','밝은 테마')]
            for i,(key,label) in enumerate(themes):
                x=509+i*224; y=511
                chosen=self.store.settings.get('theme','default')==key
                thumb=self._theme_thumbs.get(key)
                if thumb:
                    tile=thumb.resize((169,76),Image.Resampling.LANCZOS)
                    mask=Image.new('L',tile.size,0)
                    ImageDraw.Draw(mask).rounded_rectangle((0,0,168,75),radius=10,fill=255)
                    tile.putalpha(mask); layer.alpha_composite(tile,(x-vx1,y-vy1))
                layer_box(layer,(x-vx1,y-vy1,x-vx1+169,y-vy1+76),(0,0,0,0),
                          (107,210,255,255) if chosen else (111,119,186,220),10,4 if chosen else 2)
                c_text((x+84,y+82),label,13,'#F1F7FF',chosen,anchor='mt')
                c_area('setting:theme:'+key,(x,y,x+169,y+104))
            c_line((509,610,1180,610),(69,86,145,172),2)
            c_toggle('배경 애니메이션 효과','별빛과 꽃잎 장식을 표시해.',622,'effects',self.store.settings.get('effects',True))
            c_toggle('캐릭터 애니메이션','영상의 움직임을 반복 재생해. 끄면 정지해.',674,'gifplay',self.store.settings.get('gif_play',True))
            c_text((510,736),'UI 투명도',16,'#F4F7FF',True)
            pct=max(45,min(100,int(self.store.settings.get('ui_opacity',80))))
            x1,x2=763,1105; yy=754
            c_box((x1,yy-5,x2,yy+5),(43,49,101,244),None,6)
            dx=int((pct-45)/55*(x2-x1))
            c_box((x1,yy-5,x1+dx,yy+5),(120,153,255,255),None,6)
            ImageDraw.Draw(layer).ellipse((x1-vx1+dx-12,yy-vy1-12,x1-vx1+dx+12,yy-vy1+12),fill='#CCCDFF',outline='#FFFFFF',width=2)
            c_text((1176,736),f'{pct}%',17,'#FFFFFF',True,anchor='ra')
            c_area('setting:opacity',(x1-10,yy-19,x2+12,yy+19))
        elif tab=='general':
            c_text((509,279),'일반 설정',24,'#FFFFFF',True)
            c_toggle('시작할 때 업데이트 자동 확인','GitHub Releases 연결 시 새 버전이 있는지 확인해.',352,'autocheck',self.store.settings.get('check_on_launch',True))
            c_toggle('동영상 배경 재생','실행 시 네가 보낸 성곽 동영상을 재생해.',429,'gifplay',self.store.settings.get('gif_play',True))
            repo=self.store.settings.get('repo','') or 'GitHub 저장소 미연결'
            c_button('저장소 주소 설정','setting:repo',(522,523,753,572),accent='violet')
            c_text((774,539),repo[:31],15,'#D5E1FF')
            c_text((526,604),'런처 '+DISPLAY_VERSION+'  |  성장 기록기 '+display_version(self.store.state['current']),19,'#FFFFFF',True)
        elif tab=='alerts':
            c_text((509,279),'알림 설정',24,'#FFFFFF',True)
            c_toggle('새 버전 발견 알림','업데이트가 있으면 흐린 배경 위에 중앙 팝업을 띄워.',352,'notify_updates',self.store.settings.get('notify_updates',True))
            c_toggle('성장 기록기 실행 알림','기록기를 시작할 때 준비 및 로딩 화면을 표시해.',432,'notify_launch',self.store.settings.get('notify_launch',True))
            c_text((518,575),'업데이트 알림을 꺼도 상단에서 업데이트 확인이 가능해.',16,'#B7C8F1')
        elif tab=='data':
            c_text((509,279),'데이터 관리',24,'#FFFFFF',True)
            c_text((511,327),'기록·설정·개인 배경은 업데이트와 별도로 보관돼.',16,'#BED0F0')
            c_button('기록 폴더 열기','data',(520,381,812,431),accent='violet')
            c_button('새 백업 만들기','backup',(836,381,1157,431),accent='cyan')
            c_button('이전 기록 가져오기','import',(520,463,812,513),accent='violet')
            c_button('이전 버전 복구','settings-versions',(836,463,1157,513),accent='violet')
            c_text((521,590),'현재 기록기 버전: '+display_version(self.store.state['current']),17,'#C5D7FF')
        else:
            c_text((509,279),'고급 설정',24,'#FFFFFF',True)
            c_button('배경 파일 변경','setting:background',(520,366,810,421),accent='violet')
            c_button('기본 동영상 배경 복원','setting:resetbackground',(837,366,1167,421),accent='violet')
            c_button('이펙트 강도 변경','setting:strength',(520,453,810,508),accent='cyan')
            c_text((834,469),str(self.store.settings.get('effect_strength',2))+' / 3',19,'#E0E8FF',True)
            c_button('오류 기록 열기','data',(520,541,810,594),accent='violet')
            c_button('이전 런처 복구','setting:launcher_rollback',(837,541,1167,594),accent='violet')
            c_text((520,625),'게임 파일·기록 데이터를 수정하지 않는 화면 캡처 방식이야.',14,'#B5C6E9')

        crop=layer.crop((0,scroll,view_w,scroll+view_h))
        im.alpha_composite(crop,(vx1,vy1))

        if max_scroll>0:
            track=(1190,284,1200,667)
            self._panel(im,track,(24,33,79,215),(79,99,173,170),7)
            thumb_h=max(64,int((view_h/content_h)*(track[3]-track[1]-8)))
            thumb_y=track[1]+4+int((track[3]-track[1]-8-thumb_h)*(scroll/max_scroll if max_scroll else 0))
            self._panel(im,(track[0]+1,thumb_y,track[2]-1,thumb_y+thumb_h),(126,160,255,242),(202,230,255,235),7)
            text(im,(1189,256),'스크롤',11,'#93B8F7')
    def _help(self,im):
        self._panel_page(im,'도움말','성장 기록기는 게임과 별도로 실행돼. 문제가 생기면 로그를 확인해.')
        contents=[('01','기록기 실행','메인 화면의 보라색 버튼을 누르면 정확 전투력과 상세 수치 기록기가 열려.'),
                  ('02','업데이트','GitHub 저장소에 새 Release가 올라오면 빨간 버튼이 나타나.'),
                  ('03','게임 전체화면 캡처','기록기에서 DXcam 캡처 진단을 먼저 해봐. 듀얼 모니터 번호도 확인해.'),
                  ('04','기존 기록 보존','CSV·설정·배경은 user_data 폴더에 있어. 업데이트 대상과 분리돼.'),
                  ('05','복구','버전 관리에서 이전 버전을 고르면 기록 손실 없이 돌아갈 수 있어.')]
        for i,(n,title,detail) in enumerate(contents):
            y=278+i*76
            self._panel(im,(223,y,1219,y+68),(18,29,72,215),(64,81,148,147),12)
            text(im,(245,y+14),n,23,CYAN,True)
            text(im,(311,y+9),title,17,INK,True)
            text(im,(313,y+38),detail,13,MUTED)
        self._button(im,'오류 기록 폴더 열기','data',(935,675,1212,721),accent='violet')

    def _render_image(self,overlay_only=False):
        self.hit={}
        self.cta_bbox=None
        im=Image.new('RGBA',(W,H),(0,0,0,0)) if overlay_only else self._background()
        # Color themes preserve the original video and illustrated UI assets.
        theme=self.store.settings.get('theme','default')
        if theme=='dark':im.alpha_composite(Image.new('RGBA',(W,H),(2,4,18,60)))
        elif theme=='light':im.alpha_composite(Image.new('RGBA',(W,H),(123,110,190,20)))
        # Main UI: top nav on every page, no left sidebar.
        self._nav(im)
        if self.page=='home':self._home(im)
        elif self.page=='notes':self._notes(im)
        elif self.page=='versions':self._versions(im)
        elif self.page=='settings':self._settings(im)
        elif self.page=='help':self._help(im)
        self.base_img=im
        if self.modal:
            im=im.filter(ImageFilter.GaussianBlur(7))
            cover=Image.new('RGBA',(W,H),(4,8,23,140));im.alpha_composite(cover)
            self._draw_modal(im)
        return im

    def _modal_button(self,im,label,rect,key,red=False):
        if red:
            for margin,alpha in ((12,22),(7,36),(3,80)):
                layer_box(im,(rect[0]-margin,rect[1]-margin,rect[2]+margin,rect[3]+margin),
                          (255,45,93,alpha),None,14+margin)
        self._panel(im,rect,(181,27,73,247) if red else (39,54,117,236),
                    (255,109,143,255) if red else (116,149,246,235),17,shadow=22)
        x1,y1,x2,y2=rect
        text(im,((x1+x2)/2,(y1+y2)/2),label,18,'#FFFFFF',True,anchor='mm')
        self._area(key,rect)

    def _illustrated_modal(self, im, completed=False):
        """Different approved fantasy scenes for discovery and completion.

        Live text and hitboxes are drawn independently of the illustrations.
        Every control stays within the modal's 1440×810 logical bounds.
        """
        x,y,w,h=325,68,790,676
        artwork=self._done_art if completed else self._update_art
        if artwork is None:
            return False
        art=artwork.resize((w,h),Image.Resampling.LANCZOS).convert('RGBA')
        mask=Image.new('L',(w,h),0)
        ImageDraw.Draw(mask).rounded_rectangle((0,0,w-1,h-1),radius=23,fill=255)
        art.putalpha(mask)
        shadow=Image.new('RGBA',im.size,(0,0,0,0))
        ImageDraw.Draw(shadow).rounded_rectangle((x-5,y+12,x+w+5,y+h+13),radius=26,fill=(0,0,16,214))
        im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(23)))
        im.alpha_composite(art,(x,y))
        layer_box(im,(x+1,y+1,x+w-2,y+h-2),(0,0,0,0),(206,142,255,255),radius=23,width=3)
        sx=w/artwork.width;sy=h/artwork.height
        def mapped(box):
            return (x+int(box[0]*sx),y+int(box[1]*sy),x+int(box[2]*sx),y+int(box[3]*sy))

        if completed:
            # The final scene uses a resting mascot, twilight veranda and
            # BLUE/VIOLET launch action, unlike the red discovery scene.
            kind='런처' if self.modal=='restart_required' else '성장 기록기'
            version=self.launcher_manager.active() if self.modal=='restart_required' else self.store.state['current']
            info=mapped((145,407,624,503))
            layer_box(im,info,(9,14,49,255),(184,135,255,234),radius=13,width=2)
            d=ImageDraw.Draw(im)
            tick_circle=mapped((163,425,207,470))
            d.ellipse(tick_circle,fill=(16,72,53,242),outline=(88,247,170,255),width=3)
            px=x+int(186*sx);py=y+int(445*sy)
            d.line((px-10,py,px-2,py+8),fill=(129,255,186,255),width=4)
            d.line((px-2,py+8,px+13,py-11),fill=(129,255,186,255),width=4)
            text(im,(x+int(244*sx),y+int(424*sy)),kind+' 설치 버전: v'+str(version).lstrip('v'),19,'#FFFFFF',True)
            text(im,(x+int(245*sx),y+int(463*sy)),'기존 기록과 설정은 그대로 보존했어.',15,'#D8DDFB')
            primary=mapped((169,521,606,579))
            secondary=mapped((167,591,608,645))
            self._area('modal:restart' if self.modal=='restart_required' else 'modal:launch',primary)
            self._area('modal:later',secondary)
            if self.modal=='restart_required':
                layer_box(im,primary,(60,43,142,245),(199,171,255,250),radius=16,width=2)
                text(im,((primary[0]+primary[2])/2,(primary[1]+primary[3])/2),'런처 다시 시작',21,'#FFFFFF',True,anchor='mm')
        else:
            # Only the live release information is re-rendered, leaving the
            # glowing title, scenery, and illustrated red button untouched.
            version='v'+str((self.release or {}).get('version','0.0.0')).lstrip('v')
            note=mapped((141,274,493,480))
            layer_box(im,note,(13,14,51,255),(177,112,249,233),radius=12,width=2)
            text(im,(note[0]+17,note[1]+12),version,29,'#FFF6FF',True)
            d=ImageDraw.Draw(im)
            d.line((note[0]+15,note[1]+58,note[2]-15,note[1]+58),fill=(194,135,255,232),width=2)
            text(im,(note[0]+18,note[1]+68),'변경 사항',16,'#E7CEFF',True)
            notes=[]
            for source_line in (self.notes or '').replace('\r','').splitlines():
                clean=source_line.strip().lstrip('-*• ').strip()
                if clean and not clean.startswith('#'):notes.append(clean)
            if not notes:notes=['새로운 기능과 개선사항을 확인해 줘.']
            for idx,ln in enumerate(notes[:3]):
                value=ln if len(ln)<=23 else ln[:22]+'…'
                text(im,(note[0]+17,note[1]+100+idx*28),'• '+value,14,'#F0E8FF')
            kind='런처' if self.update_kind=='launcher' else '성장 기록기'
            label=mapped((117,217,540,257))
            layer_box(im,label,(11,16,54,255),(131,132,236,185),radius=10)
            text(im,((label[0]+label[2])/2,(label[1]+label[3])/2),kind+' 새 버전이 출시됐어!',16,'#FFFFFF',True,anchor='mm')
            primary=mapped((135,501,659,575))
            secondary=mapped((179,592,612,642))
            self._area('modal:install',primary)
            self._area('modal:later',secondary)

        # The first poster had a rasterized X too close to its right border;
        # replace it with a real, fully inset, vector-drawn clickable X.
        cx,cy=x+w-45,y+44
        d=ImageDraw.Draw(im)
        for radius,alpha in ((31,45),(27,94)):
            d.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),fill=(93,36,175,alpha))
        d.ellipse((cx-25,cy-25,cx+25,cy+25),fill=(22,18,67,241),outline=(206,157,255,255),width=3)
        d.line((cx-9,cy-9,cx+9,cy+9),fill=(255,255,255,255),width=3)
        d.line((cx-9,cy+9,cx+9,cy-9),fill=(255,255,255,255),width=3)
        self._area('modal:close',(cx-26,cy-26,cx+26,cy+26))
        self._illustrated_button_rect=primary
        self._illustrated_popup_rect=(x,y,x+w,y+h)
        return True

    def _update_showcase_animations(self):
        """Lightweight animated petals, pulsing button edge and fairy sparkle."""
        if not self.store.settings.get('effects',True):return
        cw=max(1,self.canvas.winfo_width());ch=max(1,self.canvas.winfo_height())
        sx,sy=cw/W,ch/H
        x1,y1,x2,y2=self._illustrated_popup_rect
        if not self.popup_petal_data:
            rnd=random.Random(1281)
            self.popup_petal_data=[{'x':rnd.uniform(x1+20,x2-22),'y':rnd.uniform(y1+20,y2-30),
                'vx':rnd.uniform(-.55,-.16),'vy':rnd.uniform(.14,.42),
                'r':rnd.uniform(2,5),'p':rnd.uniform(0,math.tau)} for _ in range(22)]
        if len(self.popup_animation_items)!=len(self.popup_petal_data):
            self.canvas.delete('popup_fx');self.popup_animation_items=[]
            for particle in self.popup_petal_data:
                self.popup_animation_items.append(self.canvas.create_oval(0,0,1,1,fill='#FFD3FA',outline='',tags=('popup_fx',)))
            self._pulse_border=self.canvas.create_rectangle(0,0,1,1,outline='#FFA2DD',width=2,tags=('popup_fx',))
            self._glow_spark=self.canvas.create_oval(0,0,1,1,fill='#BAEFFF',outline='',tags=('popup_fx',))
        strength=max(1,min(3,int(self.store.settings.get('effect_strength',2))))
        t=time.monotonic()
        for particle,item in zip(self.popup_petal_data,self.popup_animation_items):
            particle['x']+=particle['vx']*strength;particle['y']+=particle['vy']*strength
            if particle['x']<x1+12:particle['x']=x2-12
            if particle['y']>y2-12:particle['y']=y1+12
            particle['p']+=.12
            rr=particle['r']*min(sx,sy)
            px=(particle['x']+math.sin(particle['p'])*2)*sx;py=particle['y']*sy
            self.canvas.coords(item,px-rr*1.4,py-rr*.65,px+rr*1.4,py+rr*.65)
            self.canvas.itemconfigure(item,fill='#FFE2F6' if math.sin(particle['p'])>.18 else '#E4A6FF')
        bx1,by1,bx2,by2=self._illustrated_button_rect
        self.canvas.coords(self._pulse_border,(bx1+5)*sx,(by1+5)*sy,(bx2-5)*sx,(by2-5)*sy)
        self.canvas.itemconfigure(self._pulse_border,outline='#B8E9FF' if self.modal!='update' else ('#FFD9F6' if math.sin(t*3)>.2 else '#FF8FC9'),width=2)
        px=(x1+(x2-x1)*.67+math.sin(t*1.8)*13)*sx
        py=(y1+(y2-y1)*.38+math.cos(t*1.9)*8)*sy
        rr=(3+2*math.sin(t*4)**2)*min(sx,sy)
        self.canvas.coords(self._glow_spark,px-rr,py-rr,px+rr,py+rr)

    def _draw_modal(self,im):
        self.hit={}
        if self.modal=='update' and self._illustrated_modal(im, completed=False):
            return
        if self.modal in ('done','restart_required') and self._illustrated_modal(im, completed=True):
            return
        w=640; x=(W-w)//2; y=166
        self._panel(im,(x,y,x+w,642),(12,20,52,251),(191,113,233,229),20,shadow=105)
        if self.modal!='progress':
            self._area('modal:close',(x+595,y+12,x+632,y+47))
            text(im,(x+604,y+11),'×',26,'#E9E9FF',True)
        typ=self.modal
        if typ=='update':
            # Glowing sakura accents, illustrated mascot and legible release details.
            if self._sakura:paste_resize(im,self._sakura,(x+w-115,y+3,x+w-10,y+198))
            text(im,(x+42,y+35),'↓',64,'#FF709A',True)
            text(im,(x+125,y+39),'업데이트가 발견되었습니다!',27,'#FFE4F0',True)
            text(im,(x+126,y+85),('런처' if self.update_kind=='launcher' else '성장 기록기')+' 새 버전이 출시됐어.',16,'#DAE2FF')
            self._panel(im,(x+37,y+128,x+w-37,y+340),(15,25,67,247),(104,104,180,164),13)
            text(im,(x+56,y+148),display_version(self.release['version']),26,'#FFFFFF',True)
            text(im,(x+59,y+193),'변경 사항',15,'#D3BCFF',True)
            for i,line in enumerate((self.notes or '공개된 패치 노트가 없어.').splitlines()[:5]):
                text(im,(x+59,y+229+i*22),('• '+line.strip())[:28],13,'#E5E7FF')
            # Mascot illustration occupies most of the right half of the patch-note card.
            if self._mascot:
                reference_illustration(im,self._mascot,(x+327,y+141,x+w-46,y+338),12)
            self._modal_button(im,'↓  업데이트 설치하기',(x+44,y+351,x+w-44,y+409),'modal:install',True)
            self._modal_button(im,'나중에 하기',(x+44,y+418,x+w-44,y+460),'modal:later')
        elif typ=='progress':
            text(im,(x+60,y+72),'◉  업데이트 진행 중',28,INK,True)
            text(im,(x+62,y+125),self.status[:47],17,MUTED)
            steps=['최신 버전 확인','파일 다운로드','파일 검증','설치 및 적용','완료']
            for i,st in enumerate(steps):
                xx=x+69+i*111
                text(im,(xx,y+181),str(i+1),22,'#A9CBFF' if self.progress>=i*25 else '#697AA8',True)
                text(im,(xx-24,y+224),st,12,MUTED)
            vbar(im,(x+55,y+275,x+w-55,y+298),self.progress/100,(137,115,250))
            if self.download_bytes[1]:
                recv,total=self.download_bytes
                text(im,(x+60,y+315),f'{recv/(1024*1024):.1f} / {total/(1024*1024):.1f} MB',14,MUTED)
            else:text(im,(x+60,y+315),'업데이트 파일을 안전하게 검증하는 중…',14,MUTED)
            text(im,(x+61,y+394),'※ 업데이트 도중 창을 닫거나 노트북을 종료하지 마.',13,'#EAD2EE')
        elif typ=='done':
            text(im,(x+51,y+69),'✓',59,'#7DF0C5',True)
            text(im,(x+132,y+71),'업데이트 완료!',30,INK,True)
            text(im,(x+132,y+118),'새 버전이 정상적으로 설치됐어.',16,MUTED)
            text(im,(x+64,y+215),'설치 버전: '+display_version(self.store.state['current']),24,'#D6C2FF',True)
            text(im,(x+64,y+275),'기존 기록과 설정은 그대로 보존했어.',15,MUTED)
            if self._mascot:
                reference_illustration(im,self._mascot,(x+369,y+170,x+w-48,y+340),11)
            self._modal_button(im,'성장 기록기 실행',(x+48,y+356,x+w-48,y+411),'modal:launch')
            self._modal_button(im,'닫기',(x+48,y+421,x+w-48,y+465),'modal:later')
        elif typ=='launching':
            text(im,(x+55,y+83),'성장 기록기 실행 준비 중…',29,'#FFF3FF',True)
            text(im,(x+57,y+136),'설치된 기록기 파일을 확인하고 있어.',16,MUTED)
            text(im,(x+61,y+245),'도깨비의 세계 · 성장 기록기',18,'#CFB5FF',True)
            self._panel(im,(x+60,y+307,x+w-60,y+322),(21,29,68,235),(71,82,144,120),9)
            text(im,(x+61,y+339),'Windows에서 기록기 프로그램을 실행하는 중이야.',14,MUTED)
        elif typ=='loading':
            text(im,(x+48,y+38),'도깨비의 세계 · 성장 기록기',24,'#FFFFFF',True)
            text(im,(x+50,y+81),'성장 기록기를 불러오는 중이야…',17,'#C8D3F9')
            if self._loading_art:
                reference_illustration(im,self._loading_art,(x+43,y+115,x+w-43,y+346),15)
            # Indeterminate light bar: no fabricated percentage or download rate.
            self._panel(im,(x+45,y+366,x+w-45,y+387),(25,28,76,246),(80,86,146,204),10)
            pos=(time.monotonic()*.52)%1
            bx=x+49+int(pos*405)
            self._panel(im,(bx,y+370,min(x+w-49,bx+98),y+382),(147,125,255,246),None,7)
            text(im,((2*x+w)/2,y+412),'실행이 완료되면 기록기 창이 열려.',14,'#BFCBEA',anchor='mt')
        elif typ=='restart_required':
            text(im,(x+51,y+69),'✓',59,'#7DF0C5',True)
            text(im,(x+132,y+71),'런처 업데이트 완료!',30,INK,True)
            text(im,(x+58,y+145),'새 런처를 별도 폴더에 안전하게 설치했어.',17,MUTED)
            text(im,(x+58,y+196),'다시 시작하면 새 버전이 적용돼.',17,'#D8C9FF')
            text(im,(x+58,y+250),'기존 기록·설정·배경은 그대로 보존돼.',15,MUTED)
            self._modal_button(im,'런처 다시 시작',(x+48,y+350,x+w-48,y+410),'modal:restart')
            self._modal_button(im,'나중에 재시작',(x+48,y+421,x+w-48,y+465),'modal:later')
        elif typ=='launch_failed':
            text(im,(x+55,y+83),'기록기를 시작하지 못했어',27,'#FFAFCE',True)
            text(im,(x+60,y+139),self.status[:45],15,MUTED)
            self._modal_button(im,'확인',(x+60,y+365,x+w-60,y+418),'modal:later')
        elif typ=='checking':
            text(im,(x+55,y+103),'◌  최신 버전 확인 중',26,INK,True)
            text(im,(x+57,y+157),'GitHub Releases에서 최신 패치를 확인하고 있어.',15,MUTED)
            self._modal_button(im,'백그라운드에서 확인',(x+50,y+360,x+w-50,y+415),'modal:later')
        elif typ=='error':
            text(im,(x+55,y+86),'!  업데이트 확인 오류',27,'#FFC0CF',True)
            for i,line in enumerate(self.status[:160].splitlines()[:4]):
                text(im,(x+59,y+159+i*29),line[:56],15,MUTED)
            self._modal_button(im,'확인',(x+51,y+378,x+w-51,y+431),'modal:later')

    def _redraw(self):
        if not self.root.winfo_exists() or not self.needs_render:return
        cw=max(1,self.canvas.winfo_width());ch=max(1,self.canvas.winfo_height())
        self.canvas.delete('all')
        self.animation_items=[]
        self.popup_animation_items=[]
        self.cta_item=None
        self.bg_item=None
        if self.using_video and self.frame_sources and not self.modal:
            # Render controls once; reuse the transparent UI overlay while frames change.
            overlay=self._render_image(overlay_only=True)
            if cw!=W or ch!=H:
                overlay=overlay.resize((cw,ch),Image.Resampling.LANCZOS)
            self.overlay_photo=ImageTk.PhotoImage(overlay)
            self._refresh_video_background()
            self.canvas.create_image(0,0,image=self.overlay_photo,anchor='nw',tags=('interface',))
        else:
            im=self._render_image()
            if cw!=W or ch!=H:im=im.resize((cw,ch),Image.Resampling.LANCZOS)
            self.tk_image=ImageTk.PhotoImage(im.convert('RGB'))
            self.canvas.create_image(0,0,image=self.tk_image,anchor='nw',tags=('base',))
        self._paint_dynamic()
        self.needs_render=False

    def _refresh_video_background(self):
        if not self.root.winfo_exists():return
        cw=max(1,self.canvas.winfo_width());ch=max(1,self.canvas.winfo_height())
        im=self._background()
        if cw!=W or ch!=H:
            im=im.resize((cw,ch),Image.Resampling.BILINEAR)
        self.bg_photo=ImageTk.PhotoImage(im.convert('RGB'))
        if self.bg_item is None:
            self.bg_item=self.canvas.create_image(0,0,image=self.bg_photo,anchor='nw',tags=('video',))
        else:
            self.canvas.itemconfigure(self.bg_item,image=self.bg_photo)

    def _paint_dynamic(self):
        if self.modal:return
        if not self.store.settings.get('effects',True):return
        cw=max(1,self.canvas.winfo_width());ch=max(1,self.canvas.winfo_height())
        sx=cw/W;sy=ch/H
        self.animation_items=[]
        for p in self.sparkles+self.petals:
            x=p['x']*sx;y=p['y']*sy;r=p['r']*min(sx,sy)
            if p['petal']:
                oid=self.canvas.create_oval(x-r*1.3,y-r*.7,x+r*1.3,y+r*.7,
                      fill='#D6B2FA',outline='',tags=('ambient',))
            else:
                oid=self.canvas.create_oval(x-r,y-r,x+r,y+r,fill='#B6E9FF',outline='',tags=('ambient',))
            self.animation_items.append(oid)
        if self.page=='home' and self.cta_bbox:
            x1,y1,x2,y2=self.cta_bbox
            off=3
            # Subtle living sparks at the edge of the ornate button; no flat underline.
            self.cta_item=self.canvas.create_oval((x1-8)*sx,(y1+39)*sy,(x1+3)*sx,(y1+50)*sy,
                 fill='#DCC8FF',outline='',tags=('cta_glow',))
            self.canvas.create_oval((x2-6)*sx,(y2-37)*sy,(x2+5)*sx,(y2-26)*sy,
                 fill='#DCC8FF',outline='',tags=('cta_glow',))

    def _tick(self):
        if not self.root.winfo_exists():return
        sett=self.store.settings
        if self.frame_sources and len(self.frame_sources)>1 and sett.get('gif_play',True):
            if time.monotonic()>=self.gif_next:
                if self.using_video:
                    # Skip intermediate frames when a slower laptop needs extra time to render.
                    # The loop keeps the source video's original speed, not slow motion.
                    self.gif_idx=int((time.monotonic()-self.video_start)*9)%len(self.frame_sources)
                else:
                    self.gif_idx=(self.gif_idx+1)%len(self.frame_sources)
                self.gif_next=time.monotonic()+(.112 if self.using_video else .135)
                if self.using_video and self.bg_item is not None and not self.modal and not self.needs_render:
                    self._refresh_video_background()
                elif self.modal:
                    # Subdued live backdrop beneath blur at a capped rate to avoid high CPU.
                    if not hasattr(self,'_modal_next') or time.monotonic()>=self._modal_next:
                        self.needs_render=True;self._modal_next=time.monotonic()+.65
                else:
                    self.needs_render=True
        if self.needs_render:self._redraw()
        if self.modal in ('update','done','restart_required') and (self._update_art if self.modal=='update' else self._done_art) is not None:
            self._update_showcase_animations()
        if not self.modal and sett.get('effects',True):
            cw=max(1,self.canvas.winfo_width());ch=max(1,self.canvas.winfo_height())
            sx=cw/W;sy=ch/H;strength=max(1,int(sett.get('effect_strength',2)))
            arr=self.sparkles+self.petals
            if len(self.animation_items)!=len(arr):
                self.canvas.delete('ambient');self._paint_dynamic()
            for p,item in zip(arr,self.animation_items):
                p['x']=(p['x']+p['vx']*strength)%W
                p['y']=(p['y']+p['vy']*strength)%H
                p['phase']+=.045
                r=p['r']*min(sx,sy)
                x=p['x']*sx;y=p['y']*sy
                self.canvas.coords(item,x-r,y-r,x+r,y+r)
                if not p['petal']:
                    bright=math.sin(p['phase'])
                    self.canvas.itemconfigure(item,fill='#DDFDFF' if bright>.6 else '#8BBFFF' if bright<-.3 else '#B7DCFF')
            if self.page=='home':
                c='#FFFFFF' if math.sin(time.monotonic()*2)>.4 else '#C5A9FA'
                for item in self.canvas.find_withtag('cta_glow'):self.canvas.itemconfigure(item,fill=c)
        self.root.after(110,self._tick)

    def _xy(self,event):
        return event.x/max(1,self.canvas.winfo_width())*W,event.y/max(1,self.canvas.winfo_height())*H

    def _target(self,x,y):
        for key,area in reversed(list(self.hit.items())):
            a,b,c,d=area
            if a<=x<=c and b<=y<=d:return key
        return None

    def _set_hover(self,key):
        if self.hover==key:return
        self.hover=key
        self.canvas.configure(cursor='hand2' if key else 'arrow')
        if key and (key.startswith('nav:') or key in ('primary','page:close')):self._mark()

    def _motion(self,event):
        x,y=self._xy(event);self._set_hover(self._target(x,y))

    def _settings_scroll_max(self, tab=None):
        heights={'general':362,'display':548,'alerts':334,'data':360,'advanced':384}
        vy1,vy2=264,688
        tab=tab or self.settings_tab
        return max(0,heights.get(tab,vy2-vy1)-(vy2-vy1))

    def _scroll_settings(self, delta):
        if self.page!='settings' or self.modal:return
        tab=self.settings_tab
        limit=self._settings_scroll_max(tab)
        if limit<=0:return
        step=38
        current=int(self.settings_scroll.get(tab,0))
        updated=max(0,min(limit,current+delta*step))
        if updated!=current:
            self.settings_scroll[tab]=updated
            self._mark()

    def _mousewheel(self,event,direction=None):
        if self.page!='settings' or self.modal:return
        if direction is None:
            delta=-1 if getattr(event,'delta',0)>0 else 1
        else:
            delta=direction
        self._scroll_settings(delta)

    def _opacity_drag(self,event):
        if self.page!='settings' or self.settings_tab!='display':return
        x,y=self._xy(event)
        slider_y=754-int(self.settings_scroll.get('display',0))
        if slider_y-19<=y<=slider_y+19 and 738<=x<=1130:
            pct=round(45+55*max(0,min(1,(x-763)/(1105-763))))
            self.store._settings_cache['ui_opacity']=pct
            atomic_json(self.store.settings_file,self.store._settings_cache);self._mark()

    def _click(self,event):
        x,y=self._xy(event);key=self._target(x,y)
        if not key:return
        if key.startswith('nav:'):
            if self.modal=='progress':return
            self.modal=None;self.page=key.split(':')[1];self._mark();return
        if key=='page:close':
            self.modal=None;self.page='home';self._mark();return
        if key=='primary':
            if self.latest_status=='new':self._show_update()
            else:self.run_app()
        elif key=='oldapp':self.run_app()
        elif key=='news':self.page='notes';self._mark()
        elif key in ('quick:data','data'):self.open_data()
        elif key=='quick:shots':self.open_data(sub='screenshots')
        elif key=='quick:kkaebigg':self.open_kkaebigg()
        elif key=='quick:rollback':self.page='versions';self._mark()
        elif key=='check':self.check_updates()
        elif key=='backup':self.backup()
        elif key=='import':self.import_old()
        elif key.startswith('rollback:'):self.rollback(key.split(':',1)[1])
        elif key.startswith('settings-tab:'):
            self.settings_tab=key.split(':',1)[1];self._mark()
        elif key=='settings-versions':self.page='versions';self._mark()
        elif key.startswith('setting:'):
            if key=='setting:opacity':
                pct=round(45+55*max(0,min(1,(x-763)/(1105-763))))
                self.store._settings_cache['ui_opacity']=pct
                atomic_json(self.store.settings_file,self.store._settings_cache);self._mark()
            else:self.setting_action(key.split(':',1)[1])
        elif key in ('modal:close','modal:later'):
            if self.modal=='progress':return
            self.modal=None;self.page='home';self._mark()
        elif key=='modal:install':self.install_update()
        elif key=='modal:launch':self.modal=None;self._mark();self.run_app()
        elif key=='modal:restart':self._restart_launcher()

    def _escape(self,_=None):
        if self.modal and self.modal!='progress':
            self.modal=None;self.page='home';self._mark()
        elif self.page!='home' and not self.modal:
            self.page='home';self._mark()

    def _close(self):
        if self.busy:
            if not messagebox.askyesno('작업 중','다운로드 또는 설치가 진행 중이야. 종료하면 작업이 중단될 수 있어. 종료할까?',parent=self.root):return
        self.root.destroy()

    def _show_update(self):
        if not self.release or self.latest_status!='new':return
        self.modal='update';self._mark()

    def _start_auto_check(self):
        if self.store.settings.get('check_on_launch',True) and self.store.settings.get('repo'):
            self.check_updates(silent=True)

    def check_updates(self,silent=False):
        if self.busy:return
        repo=self.store.settings.get('repo','')
        if not repo:
            self.latest_status='unknown';self.status='GitHub 저장소가 아직 연결되지 않았어. 설정에서 연결해 줘.'
            if not silent:self.page='settings'
            self._mark();return
        self.latest_status='checking';self.status='GitHub Releases에서 성장 기록기와 런처 업데이트 확인 중…';self._mark()
        self._worker(lambda:get_available_releases(repo),self._got_release)

    def _got_release(self,res):
        self.available_releases=res
        candidates=[]
        app=res.get('app');launcher=res.get('launcher')
        if app and is_update(app,'app',self.store.state['current']):candidates.append(app)
        if launcher and is_update(launcher,'launcher',self.launcher_manager.active()):candidates.append(launcher)
        # Launcher changes first so new update logic is available before app updates.
        self.release=next((c for c in candidates if c['kind']=='launcher'),candidates[0] if candidates else None)
        self.update_kind=self.release['kind'] if self.release else None
        self.notes=(self.release or app or launcher or {}).get('notes','') or '이번 버전의 패치 설명이 없어.'
        self.latest_status='new' if self.release else 'latest'
        self.status=('새로운 '+('런처' if self.update_kind=='launcher' else '성장 기록기')+' 업데이트를 발견했어!'
                     if self.release else '런처와 성장 기록기가 최신 상태야.')
        self._mark()
        if self.release and self.store.settings.get('notify_updates',True):self._show_update()

    def _worker(self,task,callback):
        if self.busy:return
        self.busy=True
        def worker():
            try:self.queue.put(('done',callback,task()))
            except Exception as e:self.queue.put(('error',callback,str(e)))
        threading.Thread(target=worker,daemon=True).start()
        self.root.after(70,self._poll)

    def _poll(self):
        if not self.root.winfo_exists():return
        try:
            while True:
                item=self.queue.get_nowait()
                if item[0]=='stage':
                    self.progress=item[1]
                    self.status=item[2]
                    self._mark()
                    continue
                if item[0]=='bytes':
                    self.download_bytes=item[1:3]
                    if item[2]>0:self.progress=min(70,max(18,round(item[1]*70/item[2])))
                    self.status='업데이트 파일 다운로드 중…'
                    self._mark()
                    continue
                _,cb,val=item
                self.busy=False
                if item[0]=='error':
                    self.status=str(val)
                    self.latest_status='error' if self.modal!='progress' else self.latest_status
                    self.modal='error'
                else:cb(val)
                self._mark()
        except queue.Empty:pass
        if self.busy:self.root.after(100,self._poll)

    def install_update(self):
        if self.busy or not self.release:return
        kind=self.release.get('kind','app')
        if kind=='app' and self._running():
            messagebox.showwarning('기록기 실행 중','성장 기록기를 종료한 다음 업데이트해 줘.',parent=self.root);return
        active=self.launcher_manager.active() if kind=='launcher' else self.store.state['current']
        if not is_update(self.release,kind,active):return
        self.modal='progress';self.progress=0;self.download_bytes=(0,0)
        self.status='기존 기록을 먼저 백업하고 있어.';self._mark()
        release=self.release.copy()
        def work():
            saved=self.store.make_backup()
            self.queue.put(('stage',18,'기존 기록 백업 완료. 다운로드 준비 중…'))
            self.queue.put(('bytes',0,0))
            def on_progress(done,total):self.queue.put(('bytes',done,total))
            package=get_release_zip(release,on_progress=on_progress)
            self.queue.put(('stage',82,'다운로드 파일 검증 완료. 새 버전 설치 중…'))
            if kind=='launcher':
                version=self.launcher_manager.install(package,release['version'])
            else:
                version=self.store.install_package(package,release['version'])
            self.queue.put(('stage',96,'설치 검증 및 버전 전환 완료…'))
            return kind,version,saved
        self._worker(work,self._installed)

    def _installed(self,res):
        kind,version,_=res
        self.progress=100
        self.status='업데이트 설치 완료! 기존 설정과 기록은 안전하게 보관했어.'
        self.modal='restart_required' if kind=='launcher' else 'done'
        # After app upgrade, scan for a pending launcher update and vice versa
        self.latest_status='latest'
        self.release=None
        self._mark()

    def _restart_launcher(self):
        host=ROOT/'launch_host.pyw'
        if not host.is_file():
            messagebox.showerror('재시작 오류','런처 재시작 실행기가 없어. 기존 런처를 종료 후 다시 열어 줘.',parent=self.root)
            return
        try:
            exe=sys.executable
            if os.name=='nt' and exe.lower().endswith('python.exe'):
                alt=Path(exe).with_name('pythonw.exe')
                if alt.is_file():exe=str(alt)
            subprocess.Popen([exe,str(host)],cwd=str(ROOT),
                env={**os.environ,'DOKKAEBI_LAUNCHER_ROOT':str(ROOT)},
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.root.destroy()
        except Exception as e:messagebox.showerror('재시작 오류',str(e),parent=self.root)

    def _running(self):return self.proc is not None and self.proc.poll() is None

    def run_app(self):
        if self._running():
            self.status='성장 기록기가 이미 실행 중이야. 작업 표시줄에서 확인해 줘.';return
        entry=self.store.current_dir()/'tracker.py'
        if not entry.is_file():
            messagebox.showerror('실행 실패','기록기 프로그램 파일이 없어: '+str(entry),parent=self.root);return
        env=os.environ.copy()
        env['DOKKAEBI_DATA_DIR']=str(self.store.data)
        env['DOKKAEBI_ASSETS_DIR']=str(self.store.data/'assets')
        try:
            self.modal='launching' if self.store.settings.get('notify_launch',True) else None;self._mark()
            logfile=self.store.data/'launcher_errors.log'
            log=logfile.open('a',encoding='utf-8')
            try:
                self.proc=subprocess.Popen([sys.executable,str(entry)],cwd=entry.parent,env=env,
                            stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            finally:log.close()
            self.status='성장 기록기를 실행했어.'
            if self.modal:self.root.after(430, self._show_loading_modal)
            self.root.after(1370,lambda:self._dismiss_launch_modal())
            self.root.after(1700,self._check_launch)
        except Exception as e:
            self.modal='launch_failed';self.status=str(e);self._mark()
            messagebox.showerror('실행 실패',str(e),parent=self.root)

    def _show_loading_modal(self):
        if self.modal=='launching':self.modal='loading';self._mark()

    def _dismiss_launch_modal(self):
        if self.modal in ('launching','loading'):self.modal=None;self._mark()

    def _check_launch(self):
        if self.proc is not None and self.proc.poll() is not None:
            messagebox.showwarning('기록기 실행 오류','실행 직후 종료됐어. 오류 기록 파일을 확인해 줘.\n'+str(self.store.data/'launcher_errors.log'),parent=self.root)

    def rollback(self,version=None):
        if self._running():messagebox.showwarning('기록기 실행 중','먼저 기록기를 종료해 줘.',parent=self.root);return
        if version is None:
            opts=self.store.state.get('previous',[])
            if not opts:messagebox.showinfo('복구','아직 이전 버전이 없어.',parent=self.root);return
            version=opts[0]
        if not messagebox.askyesno('버전 복구',display_version(version)+' 버전으로 복구할까?\n데이터는 그대로 유지돼.',parent=self.root):return
        try:
            self.store.make_backup()
            self.store.set_current(version)
            self.latest_status='unknown';self.release=None
            self.status=display_version(version)+'으로 복구 완료. 기존 기록을 보존했어.'
            self._mark()
        except Exception as e:messagebox.showerror('복구 실패',str(e),parent=self.root)

    def backup(self):
        try:
            path=self.store.make_backup()
            messagebox.showinfo('백업 완료','기록 백업을 생성했어:\n'+str(path),parent=self.root)
        except Exception as e:messagebox.showerror('백업 실패',str(e),parent=self.root)

    def import_old(self):
        folder=filedialog.askdirectory(parent=self.root,title='이전 tracker.py 폴더 선택')
        if not folder:return
        try:
            names,backup=self.store.import_legacy(folder)
            messagebox.showinfo('가져오기 완료','가져온 데이터: '+(', '.join(names) or '없음')+'\n작업 전 백업: '+str(backup),parent=self.root)
        except Exception as e:messagebox.showerror('가져오기 실패',str(e),parent=self.root)

    def open_kkaebigg(self):
        """Open the official KkaebiGG public site only via the user's default browser."""
        try:
            ok=webbrowser.open('https://kkaebigg.com/',new=2)
            if ok is False:
                self.status='깨비지지 브라우저 열기에 실패했어. 주소: https://kkaebigg.com/'
            else:
                self.status='기본 브라우저에서 깨비지지 사이트를 열었어.'
        except Exception as exc:
            self.status='깨비지지 열기 실패: '+str(exc)
            messagebox.showerror('깨비지지 열기 실패',self.status,parent=self.root)
        self._mark()

    def open_data(self,sub=None):
        dst=self.store.data/(sub or '')
        dst.mkdir(parents=True,exist_ok=True)
        try:
            if sys.platform=='win32':os.startfile(str(dst))
            else:subprocess.Popen(['xdg-open',str(dst)])
        except Exception as e:messagebox.showerror('폴더 열기 실패',str(e),parent=self.root)

    def setting_action(self,key):
        cfg=self.store._settings_cache
        if key=='repo':
            name=simpledialog.askstring('GitHub Releases 저장소','저장소 주소를 소유자/저장소 형식으로 입력해 줘.\n예: myname/dokkaebi-tracker\n\n새 릴리스가 실제 게시되어야 자동 업데이트를 확인할 수 있어.',
                        parent=self.root,initialvalue=cfg.get('repo',''))
            if name is None:return
            try:
                self.store.set_repo(name)
                self.latest_status='unknown';self.release=None
                self.status='GitHub 저장소 정보를 저장했어.'
                self.check_updates(silent=True)
            except Exception as e:messagebox.showerror('저장소 오류',str(e),parent=self.root)
            return
        elif key.startswith('window_size:'):
            size_key=key.split(':',1)[1]
            if size_key not in WINDOW_SIZES:return
            cfg['window_size']=size_key
            self._apply_window_size(size_key)
        elif key.startswith('cta_size:'):
            size_key=key.split(':',1)[1]
            if size_key not in CTA_SIZES:return
            cfg['cta_size']=size_key
        elif key.startswith('theme:'):
            theme=key.split(':',1)[1]
            if theme not in ('default','dark','light'):return
            cfg['theme']=theme
        elif key in ('notify_updates','notify_launch'):
            cfg[key]=not cfg.get(key,True)
        elif key=='launcher_rollback':
            if not messagebox.askyesno('런처 버전 복구','현재 런처 대신 이전 버전으로 복구할까?\n기존 기록과 설정은 유지돼.',parent=self.root):return
            try:
                self.store.make_backup()
                v=self.launcher_manager.rollback()
                self.status='런처 이전 버전으로 복구할 준비가 됐어. 다시 시작할게.'
                self._restart_launcher()
            except Exception as e:messagebox.showerror('런처 복구 실패',str(e),parent=self.root)
            return
        elif key=='resetbackground':
            assetdir=self.store.data/'assets'
            for ext in ('.png','.gif'):(assetdir/('launcher_background'+ext)).unlink(missing_ok=True)
            self._load_background()
            self.status='원래 제공된 성곽 동영상 배경으로 복원했어.'
        elif key in ('autocheck','effects','gifplay'):
            k={'autocheck':'check_on_launch','effects':'effects','gifplay':'gif_play'}[key]
            cfg[k]=not cfg.get(k,False)
        elif key=='strength':
            cfg['effect_strength']=int(cfg.get('effect_strength',2))%3+1
        elif key=='background':
            path=filedialog.askopenfilename(parent=self.root,title='배경 그림 또는 애니메이션 GIF 선택',
                      filetypes=[('이미지·움직이는 GIF','*.gif *.png *.jpg *.jpeg *.webp *.bmp'),('모든 파일','*.*')])
            if not path:return
            try:
                path=Path(path)
                with Image.open(path) as im:
                    if im.width*im.height>12_000_000:raise ValueError('이미지 크기는 1200만 화소 이하로 해줘.')
                    if im.format not in ('PNG','GIF','JPEG','WEBP','BMP'):raise ValueError('지원하지 않는 이미지 파일이야.')
                    if im.format=='GIF' and getattr(im,'n_frames',1)>1 and path.stat().st_size>30_000_000:
                        raise ValueError('GIF 용량은 30MB 이하로 해줘.')
                    ext='.gif' if im.format=='GIF' and getattr(im,'n_frames',1)>1 else '.png'
                    assetdir=self.store.data/'assets';assetdir.mkdir(parents=True,exist_ok=True)
                    dst=assetdir/('launcher_background'+ext)
                    tmp=dst.with_suffix('.tmp'+ext)
                    if ext=='.png':im.convert('RGB').save(tmp,format='PNG')
                    else:shutil.copyfile(path,tmp)
                    os.replace(tmp,dst)
                    (assetdir/('launcher_background'+('.png' if ext=='.gif' else '.gif'))).unlink(missing_ok=True)
                self._load_background()
                self.status='사용자 지정 배경을 적용했어. 기본 MP4 배경으로 돌아가려면 사용자 지정 배경 파일을 제거해 줘.'
            except Exception as e:messagebox.showerror('배경 설정 실패',str(e),parent=self.root)
            self._mark();return
        atomic_json(self.store.settings_file,cfg)
        self._mark()


def main():
    root=tk.Tk()
    try:Launcher(root)
    except Exception as exc:
        messagebox.showerror('런처 시작 실패',str(exc)+'\n'+traceback.format_exc(),parent=root)
        raise
    root.mainloop()

if __name__=='__main__':main()
