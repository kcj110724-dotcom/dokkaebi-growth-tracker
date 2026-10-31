"""도깨비의 세계 화면 기반 성장 기록기 v5.

Only captures a user-selected monitor/rectangle. Never reads game memory or sends
input to the game. Data stays in this folder. OCR needs Tesseract installed.
"""
import csv
import os
import json
import math
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, filedialog

import mss
from PIL import Image, ImageTk, ImageGrab, ImageStat
import pytesseract
from pynput import keyboard
from ocr_utils import STATS, ALL_FIELDS, read_power_hud, read_power_exact, read_stat_rows

BASE = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get('DOKKAEBI_DATA_DIR', str(BASE))).resolve()
DATA_ROOT.mkdir(parents=True, exist_ok=True)
CONFIG = DATA_ROOT / 'config.json'
POWER_LOG = DATA_ROOT / 'combat_power.csv'
STAT_LOG = DATA_ROOT / 'stat_changes.csv'
SNAP_LOG = DATA_ROOT / 'stat_snapshots.csv'
STAT_CACHE = DATA_ROOT / 'stat_latest.json'
APP_NAME='도깨비의 세계 · 전투력/상세 능력치 기록기 v5'
DEFAULT={'interval':30,'monitor_index':1,'capture_method':'MSS',
         'tesseract_path':r'C:\Program Files\Tesseract-OCR\tesseract.exe',
         'font_size':14,'region_power':None,'region_power_detail':None,'region_stats':None,
         'auto_source':'전투력(상세창)',
         'key_auto':'F9','mods_auto':'없음','key_now':'F10','mods_now':'없음'}
KEY_NAMES = (
    [f'F{i}' for i in range(1,25)] + list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')+
    [str(i) for i in range(10)] + [f'Num {i}' for i in range(10)] +
    ['Num +','Num -','Num *','Num /','Num .','Num Enter',
     'Space','Enter','Tab','Backspace','Escape','CapsLock',
     'Insert','Delete','Home','End','Page Up','Page Down',
     'Up','Down','Left','Right','Print Screen','Scroll Lock','Pause',
     '`','-','=','[',']','\\',';',"'",',','.','/']
)
MOD_OPTIONS=['없음','Ctrl','Alt','Shift','Ctrl+Shift','Ctrl+Alt','Alt+Shift','Ctrl+Alt+Shift']

# Windows virtual key codes for base keys. Pynput's .vk helps us distinguish numpad keys.
SPECIAL_VK={
    'Backspace':8,'Tab':9,'Enter':13,'Pause':19,'CapsLock':20,'Escape':27,
    'Space':32,'Page Up':33,'Page Down':34,'End':35,'Home':36,
    'Left':37,'Up':38,'Right':39,'Down':40,'Print Screen':44,
    'Insert':45,'Delete':46,'Scroll Lock':145,
    'Num *':106,'Num +':107,'Num -':109,'Num .':110,'Num /':111,'Num Enter':108,
    '`':192,'-':189,'=':187,'[':219,']':221,'\\':220,';':186,"'":222,
    ',':188,'.':190,'/':191,
}
VK_TO_NAME={v:k for k,v in SPECIAL_VK.items()}
VK_TO_NAME.update({112+i:f'F{i+1}' for i in range(24)})
VK_TO_NAME.update({96+i:f'Num {i}' for i in range(10)})
VK_TO_NAME.update({48+i:str(i) for i in range(10)})
VK_TO_NAME.update({65+i:chr(65+i) for i in range(26)})
KEY_SYM={'esc':'Escape','space':'Space','enter':'Enter','return':'Enter',
         'tab':'Tab','backspace':'Backspace','delete':'Delete',
         'insert':'Insert','home':'Home','end':'End',
         'page_up':'Page Up','page_down':'Page Down','caps_lock':'CapsLock',
         'up':'Up','down':'Down','left':'Left','right':'Right',
         'print_screen':'Print Screen','scroll_lock':'Scroll Lock','pause':'Pause'}


def key_name(key):
    vk=getattr(key,'vk',None)
    if vk in VK_TO_NAME: return VK_TO_NAME[vk]
    n=getattr(key,'name',None)
    if n:
        if n in KEY_SYM:return KEY_SYM[n]
        if n.startswith('f') and n[1:].isdigit():return 'F'+n[1:]
    ch=getattr(key,'char',None)
    if isinstance(ch,str) and len(ch)==1:
        if ch.isalpha():return ch.upper()
        if ch in KEY_NAMES:return ch
    return None


def mod_name(key):
    name=getattr(key,'name','') or ''
    if 'ctrl' in name:return 'Ctrl'
    if 'alt' in name:return 'Alt'
    if 'shift' in name:return 'Shift'
    return None


def chord(key, mods):
    return '+'.join([m for m in ('Ctrl','Alt','Shift') if m in mods]+[key])


def as_text_value(value,unit):
    if unit=='%':return ('%g' % value) + '%'
    return f'{int(value):,}'


def now_iso():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def append_rows(filename,fields,rows):
    if not rows:return
    is_new=(not filename.exists() or filename.stat().st_size==0)
    with filename.open('a', newline='', encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
        if is_new:w.writeheader()
        w.writerows(rows)
        f.flush()


class Tracker:
    def __init__(self,root):
        self.root=root
        root.title(APP_NAME)
        root.geometry('1060x730')
        root.minsize(850,600)
        self.cfg=DEFAULT.copy()
        if CONFIG.exists():
            try:self.cfg.update(json.loads(CONFIG.read_text(encoding='utf-8')))
            except (OSError,ValueError):pass
        # First-run: optionally inherit measured ROI/config (never overwrite old logs).
        # Prevent importing v3's incorrect power readings into the new dataset.
        if not CONFIG.exists():
            for old in (BASE.parent/'dokkaebi_tracker_v4'/'config.json',
                        BASE.parent/'dokkaebi_tracker_v3'/'config.json'):
                if old.exists():
                    try:
                        legacy=json.loads(old.read_text(encoding='utf-8'))
                        for k in ('region_power','region_power_detail','region_stats','monitor_index',
                                  'capture_method','tesseract_path','font_size','interval',
                                  'key_auto','mods_auto','key_now','mods_now'):
                            if k in legacy:self.cfg[k]=legacy[k]
                        break
                    except (OSError,ValueError,TypeError):pass
        if not self.cfg.get('region_power'):
            for old in (BASE.parent/'dokkaebi_tracker_v3'/'config.json', BASE.parent/'dokkaebi_tracker'/'config.json'):
                if old.exists():
                    try:
                        legacy=json.loads(old.read_text(encoding='utf-8'))
                        self.cfg['region_power']=legacy.get('region')
                        if legacy.get('tesseract_path'):self.cfg['tesseract_path']=legacy['tesseract_path']
                        break
                    except Exception:pass
        self.events=queue.Queue()
        self.active=False;self.busy=False;self.next_scan=0
        self.pending_power=None;self.pending_approx=False;self.pending_count=0;self.pending_target=None;self.confirming=False
        self.last_power,self.last_power_approx,self.power_sources=self.load_power()
        self.stat_cache=self.load_stats()
        with mss.mss() as s:self.monitors=[dict(m) for m in s.monitors[1:]]
        if not self.monitors:raise RuntimeError('캡처 가능한 모니터가 없습니다.')
        self.monitors_label=[f'모니터 {i+1}: {m["width"]}×{m["height"]} ({m["left"]},{m["top"]})' for i,m in enumerate(self.monitors)]
        self.monitor_var=tk.StringVar(value=self.monitors_label[min(len(self.monitors)-1,max(0,int(self.cfg['monitor_index'])-1))])
        self.capture_method=tk.StringVar(value=self.cfg['capture_method'])
        self.interval_var=tk.StringVar(value=str(self.cfg['interval']))
        self.tess_var=tk.StringVar(value=self.cfg['tesseract_path'])
        self.font_var=tk.IntVar(value=int(self.cfg.get('font_size',14)))
        self.mod_auto=tk.StringVar(value=self.cfg.get('mods_auto','없음'))
        self.mod_now=tk.StringVar(value=self.cfg.get('mods_now','없음'))
        self.key_auto=tk.StringVar(value=self.cfg.get('key_auto','F9'))
        self.key_now=tk.StringVar(value=self.cfg.get('key_now','F10'))
        self.region_target=tk.StringVar(value='전투력(상세창)')
        self.measure_target=tk.StringVar(value='전투력(상세창)')
        self.auto_source=tk.StringVar(value=self.cfg.get('auto_source','전투력(상세창)'))
        self.status=tk.StringVar(value='준비 완료 · 측정 영역을 지정해 줘')
        self.power_label=tk.StringVar(value=self.describe_power())
        self.region_label=tk.StringVar(value=self.describe_regions())
        self.button_auto_text=tk.StringVar()
        self.button_now_text=tk.StringVar()
        self.log_rows=[]
        self.make_ui()
        self.apply_font(int(self.font_var.get()))
        self.update_hotkey_labels()
        self.update_stats_display()
        self._held=set();self._mods=set();self._hotkey_ts=0
        self.listener=keyboard.Listener(on_press=self.on_key_down,on_release=self.on_key_up)
        try:self.listener.start()
        except Exception as ex:self.status.set(f'단축키 리스너 오류: {ex} (버튼은 사용 가능)')
        root.after(150,self.tick)
        root.protocol('WM_DELETE_WINDOW',self.close)

    def make_ui(self):
        hdr=ttk.Frame(self.root,padding=(16,10));hdr.pack(fill='x')
        ttk.Label(hdr,text=APP_NAME,style='Title.TLabel').pack(anchor='w')
        ttk.Label(hdr,textvariable=self.status,style='Status.TLabel',wraplength=970).pack(anchor='w',pady=(5,0))
        tabs=ttk.Notebook(self.root);tabs.pack(fill='both',expand=True,padx=12,pady=(0,10))
        main=ttk.Frame(tabs,padding=12);settings=ttk.Frame(tabs,padding=12)
        tabs.add(main,text='  측정 및 기록  ');tabs.add(settings,text='  설정·글씨·단축키  ')

        row=ttk.Frame(main);row.pack(fill='x',pady=(2,10))
        ttk.Label(row,text='마지막 전투력:').pack(side='left',padx=(0,8))
        ttk.Label(row,textvariable=self.power_label,style='Power.TLabel').pack(side='left')
        ttk.Button(row,text='기록 폴더 열기',command=self.open_folder).pack(side='right')
        group=ttk.LabelFrame(main,text='① 화면 영역 지정',padding=12)
        group.pack(fill='x',pady=6)
        ttk.Label(group,text='선택할 영역').grid(row=0,column=0,sticky='w',padx=5,pady=4)
        ttk.Combobox(group,textvariable=self.region_target,values=['전투력(HUD)','전투력(상세창)','상세 수치 열'],state='readonly',width=17).grid(row=0,column=1,sticky='w',padx=5)
        ttk.Button(group,text='5초 후 게임 화면 캡처 → 드래그 선택',command=self.choose_region).grid(row=0,column=2,padx=10,sticky='w')
        ttk.Label(group,textvariable=self.region_label,wraplength=930).grid(row=1,column=0,columnspan=3,sticky='w',padx=5,pady=5)
        ttk.Label(group,text='정확한 전투력: 캐릭터 정보창을 열고 좌측 상단의 주황색 숫자만 드래그해. HUD의 K 단위는 참고용이야.',
                  style='Hint.TLabel',wraplength=930).grid(row=2,column=0,columnspan=3,sticky='w',padx=5)
        ttk.Label(group,text='상세 수치 열: 방어 탭 오른쪽 숫자 10줄을 통째로 지정(별 아이콘 제외). 공격·방어·기타에서 재사용해.',
                  style='Hint.TLabel',wraplength=930).grid(row=3,column=0,columnspan=3,sticky='w',padx=5)
        group.columnconfigure(2,weight=1)

        group=ttk.LabelFrame(main,text='② 측정',padding=12);group.pack(fill='x',pady=6)
        ttk.Label(group,text='수동 측정 화면').grid(row=0,column=0,padx=5,sticky='w')
        ttk.Combobox(group,textvariable=self.measure_target,values=['전투력(HUD)','전투력(상세창)','공격','방어','기타'],state='readonly',width=13).grid(row=0,column=1,padx=5,sticky='w')
        ttk.Button(group,textvariable=self.button_now_text,command=self.measure_manual).grid(row=0,column=2,padx=5,sticky='w')
        ttk.Button(group,textvariable=self.button_auto_text,command=self.toggle).grid(row=0,column=3,padx=5,sticky='w')
        ttk.Label(group,text='자동 측정 대상').grid(row=1,column=0,sticky='w',padx=5,pady=6)
        ttk.Combobox(group,textvariable=self.auto_source,values=['전투력(상세창)','전투력(HUD)'],
                     state='readonly',width=18).grid(row=1,column=1,sticky='w',padx=5)
        ttk.Label(group,text='추천: 전투력(상세창). 창이 닫혀 있으면 측정을 건너뛰어. HUD는 근삿값만 기록해.',
                  style='Hint.TLabel',wraplength=550).grid(row=1,column=2,columnspan=2,sticky='w',padx=5)
        ttk.Label(group,text='자동 감시는 선택한 전투력 영역만 주기적으로 읽어. 상세 능력치 24개는 탭을 열고 수동 측정해.',
                  style='Hint.TLabel',wraplength=920).grid(row=2,column=0,columnspan=4,sticky='w',padx=5,pady=(5,2))
        group.columnconfigure(3,weight=1)
        group=ttk.LabelFrame(main,text='③ 최근 기록 · 상세 능력치',padding=8);group.pack(fill='both',expand=True,pady=6)
        upper=ttk.Frame(group);upper.pack(fill='x')
        self.stat_summary=tk.StringVar(value='상세 능력치: 기록 없음')
        ttk.Label(upper,textvariable=self.stat_summary).pack(side='left')
        ttk.Button(upper,text='전체 능력치 보기',command=self.show_latest).pack(side='right',padx=5)
        box=ttk.Frame(group);box.pack(fill='both',expand=True,pady=8)
        self.recent=tk.Listbox(box,height=9,activestyle='none')
        self.recent.pack(side='left',fill='both',expand=True)
        scr=ttk.Scrollbar(box,orient='vertical',command=self.recent.yview);scr.pack(side='right',fill='y')
        self.recent.configure(yscrollcommand=scr.set)
        self.add_recent('측정하면 전투력과 상세 능력치 변화가 여기에 표시돼.')

        grid=ttk.Frame(settings);grid.pack(fill='both',expand=True)
        for x in (0,1):grid.columnconfigure(x,weight=1)
        style=ttk.LabelFrame(grid,text='화면·OCR',padding=12);style.grid(row=0,column=0,sticky='nsew',padx=6,pady=6)
        ttk.Label(style,text='캡처할 모니터').pack(anchor='w')
        ttk.Combobox(style,textvariable=self.monitor_var,values=self.monitors_label,state='readonly',width=44).pack(fill='x',pady=(0,8))
        ttk.Label(style,text='캡처 방식').pack(anchor='w')
        ttk.Combobox(style,textvariable=self.capture_method,values=['MSS','ImageGrab'],state='readonly').pack(fill='x',pady=(0,8))
        ttk.Label(style,text='Tesseract 실행 파일 경로').pack(anchor='w')
        ttk.Entry(style,textvariable=self.tess_var).pack(fill='x',pady=(0,8))
        ttk.Label(style,text='자동 측정 간격 (초)').pack(anchor='w')
        ttk.Spinbox(style,textvariable=self.interval_var,from_=5,to=3600,width=8).pack(anchor='w',pady=(0,8))
        style=ttk.LabelFrame(grid,text='글씨 크기',padding=12);style.grid(row=0,column=1,sticky='nsew',padx=6,pady=6)
        ttk.Label(style,text='프로그램 전체 글씨 크기').pack(anchor='w',pady=5)
        size=ttk.Frame(style);size.pack(fill='x')
        ttk.Spinbox(size,textvariable=self.font_var,from_=10,to=26,increment=1,width=6).pack(side='left')
        ttk.Label(size,text='pt (10~26)').pack(side='left',padx=8)
        ttk.Button(style,text='크기 바로 적용',command=self.apply_font_from_ui).pack(anchor='w',pady=10)
        ttk.Label(style,text='버튼, 탭, 표, 안내 글씨까지 함께 확대해.\n창 크기도 자유롭게 늘릴 수 있어.',wraplength=350).pack(anchor='w')
        keys=ttk.LabelFrame(grid,text='단축키 · 목록에서 자유롭게 선택',padding=12)
        keys.grid(row=1,column=0,columnspan=2,sticky='ew',padx=6,pady=6)
        ttk.Label(keys,text='동작').grid(row=0,column=0,sticky='w',padx=5)
        ttk.Label(keys,text='조합키').grid(row=0,column=1,sticky='w',padx=5)
        ttk.Label(keys,text='기본 키').grid(row=0,column=2,sticky='w',padx=5)
        for i,(label,mod_var,key_var) in enumerate([
            ('자동 시작 / 중지',self.mod_auto,self.key_auto),
            ('지금 측정',self.mod_now,self.key_now)],start=1):
            ttk.Label(keys,text=label).grid(row=i,column=0,padx=5,pady=5,sticky='w')
            ttk.Combobox(keys,textvariable=mod_var,values=MOD_OPTIONS,state='readonly',width=17).grid(row=i,column=1,padx=5,pady=5)
            ttk.Combobox(keys,textvariable=key_var,values=KEY_NAMES,state='readonly',width=20).grid(row=i,column=2,padx=5,pady=5)
        ttk.Label(keys,text='일부 Windows 예약 단축키는 사용할 수 없어. 단일 문자키는 게임 조작과 겹칠 수 있어.',
                  wraplength=850,style='Hint.TLabel').grid(row=3,column=0,columnspan=4,sticky='w',pady=5)
        ttk.Button(settings,text='모든 설정 저장',command=self.save_settings).pack(anchor='e',padx=14,pady=8)

    def apply_font_from_ui(self):
        self.apply_font(self.font_var.get())
        self.save_settings()

    def apply_font(self,size):
        try:size=int(size)
        except (ValueError,TypeError):size=14
        if size<10 or size>26:
            messagebox.showwarning('글씨 크기','10~26 사이 숫자를 입력해 줘.');return
        for f in ('TkDefaultFont','TkTextFont','TkHeadingFont','TkMenuFont','TkCaptionFont','TkSmallCaptionFont','TkFixedFont'):
            try:tkfont.nametofont(f).configure(family='맑은 고딕',size=size)
            except tk.TclError:pass
        style=ttk.Style()
        style.configure('.',font=('맑은 고딕',size))
        style.configure('Title.TLabel',font=('맑은 고딕',size+4,'bold'))
        style.configure('Power.TLabel',font=('맑은 고딕',size+4,'bold'))
        style.configure('Status.TLabel',foreground='#155b99')
        style.configure('Hint.TLabel',foreground='#666666')
        style.configure('TButton',padding=(8,max(5,size//3)))
        style.configure('TNotebook.Tab',padding=(12,max(5,size//3)))
        style.configure('Treeview',font=('맑은 고딕',size),rowheight=max(24,size*2))
        style.configure('Treeview.Heading',font=('맑은 고딕',size,'bold'))
        self.cfg['font_size']=size
        # Keep enlarged text usable on ordinary 1920x1080 desktops.
        if size>=19:
            w=min(self.root.winfo_screenwidth()-80, 1100+(size-18)*65)
            h=min(self.root.winfo_screenheight()-100, 750+(size-18)*20)
            self.root.geometry(f'{w}x{h}')
        self.root.update_idletasks()

    def describe_power(self):
        return '기록 없음' if self.last_power is None else f'{self.last_power:,}' + (' (약)' if self.last_power_approx else ' (정확)')

    def describe_regions(self):
        return ('HUD 전투력: '+('설정됨' if self.cfg.get('region_power') else '미설정') +
                ' | 상세창 전투력: '+('설정됨' if self.cfg.get('region_power_detail') else '미설정')+
                ' | 상세 수치 10줄: '+('설정됨' if self.cfg.get('region_stats') else '미설정'))

    def load_power(self):
        sources={}
        last=None
        if POWER_LOG.exists():
            try:
                with POWER_LOG.open(newline='',encoding='utf-8-sig') as f:
                    for row in csv.DictReader(f):
                        last=row
                        approx=row.get('source','').endswith('_approx')
                        sources['approx' if approx else 'exact']=int(row['combat_power'])
            except (OSError,ValueError,KeyError):pass
        if not last:return None,False,sources
        try:
            return int(last['combat_power']),last.get('source','').endswith('_approx'),sources
        except (ValueError,KeyError):return None,False,sources

    def load_stats(self):
        if not STAT_CACHE.exists():return {}
        try:
            obj=json.loads(STAT_CACHE.read_text(encoding='utf-8'))
            return obj if isinstance(obj,dict) else {}
        except (OSError,ValueError):return {}

    def update_stats_display(self):
        self.stat_summary.set(f'상세 능력치: {len(self.stat_cache)}/24개 기록됨')

    def open_folder(self):
        import os
        os.startfile(str(BASE))

    def add_recent(self,msg):
        self.recent.insert(0,msg)
        while self.recent.size()>200:self.recent.delete(tk.END)

    def save_settings(self):
        try:
            interval=int(self.interval_var.get())
            if not (5<=interval<=3600):raise ValueError()
        except ValueError:
            messagebox.showerror('설정 오류','자동 측정 간격은 5~3600초야.');return False
        if self.key_auto.get() not in KEY_NAMES or self.key_now.get() not in KEY_NAMES:
            messagebox.showerror('설정 오류','단축키는 목록에서 골라줘.');return False
        combo1=chord(self.key_auto.get(),self.mod_auto.get().split('+') if self.mod_auto.get()!='없음' else [])
        combo2=chord(self.key_now.get(),self.mod_now.get().split('+') if self.mod_now.get()!='없음' else [])
        if combo1==combo2:
            messagebox.showerror('설정 오류','두 기능에는 서로 다른 단축키를 설정해야 해.');return False
        reserved={'Alt+F4','Alt+Tab','Ctrl+Alt+Delete','Ctrl+Shift+Escape'}
        if combo1 in reserved or combo2 in reserved:
            messagebox.showerror('설정 오류','Windows 예약 단축키는 사용할 수 없어.');return False
        if self.monitor_var.get() not in self.monitors_label:
            messagebox.showerror('설정 오류','모니터를 선택해 줘.');return False
        self.cfg.update(auto_source=self.auto_source.get(),interval=interval,monitor_index=self.monitors_label.index(self.monitor_var.get())+1,
                        capture_method=self.capture_method.get(),tesseract_path=self.tess_var.get().strip().strip('"'),
                        key_auto=self.key_auto.get(),mods_auto=self.mod_auto.get(),
                        key_now=self.key_now.get(),mods_now=self.mod_now.get())
        try:self.cfg['font_size']=int(self.font_var.get())
        except ValueError:pass
        try:CONFIG.write_text(json.dumps(self.cfg,indent=2,ensure_ascii=False),encoding='utf-8')
        except OSError as e:messagebox.showerror('저장 오류',str(e));return False
        self.update_hotkey_labels()
        self.status.set('설정을 저장했어. 프로그램을 다시 켜도 유지돼.')
        return True

    def update_hotkey_labels(self):
        a=chord(self.key_auto.get(),self.mod_auto.get().split('+') if self.mod_auto.get()!='없음' else [])
        n=chord(self.key_now.get(),self.mod_now.get().split('+') if self.mod_now.get()!='없음' else [])
        self.button_auto_text.set(f'{a} · 자동 시작/중지')
        self.button_now_text.set(f'{n} · 지금 측정')

    def capture(self,region):
        if self.cfg['capture_method']=='ImageGrab':
            bbox=(region['left'],region['top'],region['left']+region['width'],region['top']+region['height'])
            return ImageGrab.grab(bbox=bbox,all_screens=True).convert('RGB')
        with mss.mss() as s:
            sh=s.grab(region)
            return Image.frombytes('RGB',sh.size,sh.rgb)

    def choose_region(self):
        if self.busy:return
        if not self.save_settings():return
        self.status.set('5초 후 게임 모니터를 캡처할게. 게임에서 숫자가 보이게 해줘.')
        self.root.iconify()
        self.root.after(5000,self.show_selection)

    def show_selection(self):
        try:
            monitor=self.monitors[self.cfg['monitor_index']-1]
            image=self.capture(monitor)
        except Exception as e:
            self.root.deiconify();messagebox.showerror('캡처 오류',str(e));return
        self.root.deiconify()
        self._show_selection_image(image, monitor)

    def _show_selection_image(self, image, monitor):
        win=tk.Toplevel(self.root)
        target=self.region_target.get()
        win.title(('방어 탭 오른쪽 숫자 10줄 전체' if target=='상세 수치 열' else '전투력 숫자 한 줄')+'를 드래그해 선택')
        scale=min(1120/image.width,700/image.height,1)
        w=max(1,round(image.width*scale));h=max(1,round(image.height*scale))
        photo=ImageTk.PhotoImage(image.resize((w,h)))
        canvas=tk.Canvas(win,width=w,height=h,cursor='crosshair',highlightthickness=0)
        canvas.pack(padx=10,pady=8)
        canvas.create_image(0,0,anchor='nw',image=photo);canvas.image=photo
        ttk.Label(win,text=('전투력: 숫자 글자만 여백을 포함해 선택'
                            if target!='상세 수치 열' else '방어 상세: 첫 번째 숫자 위부터 10번째 숫자 아래까지. 별 아이콘은 빼고 선택'),
                  wraplength=1100).pack(pady=8)
        drag={'start':None,'rect':None}
        def start(e):
            drag['start']=(e.x,e.y)
            if drag['rect']:canvas.delete(drag['rect'])
            drag['rect']=canvas.create_rectangle(e.x,e.y,e.x,e.y,outline='red',width=2)
        def move(e):
            if drag['start']:
                a,b=drag['start'];canvas.coords(drag['rect'],a,b,e.x,e.y)
        def end(e):
            if not drag['start']:return
            ax,ay=drag['start']
            x0,x1=sorted((max(0,min(w,ax)),max(0,min(w,e.x))))
            y0,y1=sorted((max(0,min(h,ay)),max(0,min(h,e.y))))
            if x1-x0<15 or y1-y0<(50 if target=='상세 수치 열' else 8):
                messagebox.showwarning('선택 영역','영역이 너무 작아. 숫자 열을 넉넉히 선택해 줘.',parent=win);return
            region={'left':monitor['left']+round(x0/scale),'top':monitor['top']+round(y0/scale),
                    'width':round((x1-x0)/scale),'height':round((y1-y0)/scale)}
            if target=='상세 수치 열' and region['height']<300:
                messagebox.showwarning('상세 영역','숫자 10줄 전체가 들어가도록 세로로 길게 선택해 줘.',parent=win);return
            self.cfg['region_stats' if target=='상세 수치 열' else ('region_power_detail' if target=='전투력(상세창)' else 'region_power')]=region
            if target!='상세 수치 열':
                self.measure_target.set(target)
                if target=='전투력(상세창)': self.auto_source.set(target)
            self.save_settings();self.region_label.set(self.describe_regions())
            self.status.set('영역 선택 완료. 현재 화면에 맞는 측정 버튼으로 확인해 봐.')
            win.destroy()
        canvas.bind('<Button-1>',start);canvas.bind('<B1-Motion>',move);canvas.bind('<ButtonRelease-1>',end)

    def _on_key_press_name(self, key):
        m=mod_name(key)
        if m:self._mods.add(m);return
        kn=key_name(key)
        if not kn:return
        combo=chord(kn,self._mods)
        if combo in self._held:return
        self._held.add(combo)
        if combo==chord(self.cfg['key_auto'],[] if self.cfg['mods_auto']=='없음' else self.cfg['mods_auto'].split('+')):
            self.events.put('toggle')
        elif combo==chord(self.cfg['key_now'],[] if self.cfg['mods_now']=='없음' else self.cfg['mods_now'].split('+')):
            self.events.put('manual')

    def on_key_down(self,key):
        try:self._on_key_press_name(key)
        except Exception as e:self.events.put(('warning',f'단축키 오류: {e}'))

    def on_key_up(self,key):
        try:
            m=mod_name(key)
            if m:self._mods.discard(m)
            else:
                kn=key_name(key)
                if kn:
                    self._held={x for x in self._held if x.split('+')[-1]!=kn}
        except Exception:pass

    def toggle(self):
        if not self.save_settings():return
        chosen=self.cfg.get('auto_source','전투력(상세창)')
        target_region='region_power_detail' if chosen=='전투력(상세창)' else 'region_power'
        if not self.cfg.get(target_region):
            self.status.set(f'먼저 {chosen} 측정 영역을 지정해 줘.');return
        self.active=not self.active;self.next_scan=0
        self.pending_power=None;self.pending_count=0;self.pending_target=None;self.confirming=False
        self.status.set(f'자동 감시 켜짐 · {chosen} (변경된 값만 저장)' if self.active else '자동 감시 꺼짐 · 기존 기록은 유지돼')

    def measure_manual(self):
        target=self.measure_target.get()
        if self.busy:self.status.set('이전 측정을 처리 중이야.');return
        region=self.cfg.get('region_stats' if target in STATS else ('region_power_detail' if target=='전투력(상세창)' else 'region_power'))
        if not region:self.status.set(f'{target} 측정 영역이 미설정이야. 먼저 선택해 줘.');return
        self.scan(target,True)

    def scan(self,target,manual=False):
        if self.busy:return
        self.busy=True
        self.status.set(f'{target} 화면을 읽는 중... 측정이 끝날 때까지 해당 화면을 유지해 줘.')
        region=self.cfg['region_stats' if target in STATS else ('region_power_detail' if target=='전투력(상세창)' else 'region_power')]
        config=dict(self.cfg)
        def worker():
            try:
                path=config.get('tesseract_path')
                if path:pytesseract.pytesseract.tesseract_cmd=path
                img=self.capture(region)
                if target=='전투력(상세창)':value=read_power_exact(img)
                elif target=='전투력(HUD)':value=read_power_hud(img)
                else:value=read_stat_rows(img,target)
                self.events.put(('measured',target,manual,value))
            except Exception as e:self.events.put(('error',f'{type(e).__name__}: {e}'))
        threading.Thread(target=worker,daemon=True).start()

    def handle_power(self,result,manual,target):
        if result is None:
            if target=='전투력(상세창)':
                self.status.set('정보창 숫자를 읽지 못했어 · 정보창이 닫혀 있거나 영역이 맞지 않으면 저장하지 않아.')
            else:self.status.set('HUD K 숫자 인식 실패 · 영역·모니터를 확인해 줘.')
            self.pending_power=None;self.pending_count=0;self.pending_target=None;self.confirming=False
            return
        value,approx=result
        info='K 단위 근삿값' if approx else '정확한 표시 수치'
        # On manual scanning, schedule a double check for OCR glitches too.
        if manual:
            self.pending_power=value;self.pending_approx=approx;self.pending_count=1;self.pending_target=target;self.confirming=True
            self.status.set(f'{value:,} ({info}) 감지 · 재확인 중...')
            self.next_scan=max(self.next_scan,time.monotonic()+3)
            self.root.after(850,lambda:self.scan(target,False))
            return
        if result==(self.pending_power,self.pending_approx) and target==self.pending_target:self.pending_count+=1
        else:self.pending_power,self.pending_approx,self.pending_count=value,approx,1;self.pending_target=target
        if self.pending_count<2:
            if not self.confirming:
                self.confirming=True
                self.status.set(f'{value:,} ({info}) 감지 · 1초 후 재검증할게.')
                self.root.after(850,lambda:self.scan(target,False))
            else:
                # This was the second read and did not agree: discard safely.
                self.confirming=False
                self.pending_count=0
                self.status.set('연속 측정 결과가 달라서 저장하지 않았어. 화면을 다시 확인해 줘.')
            return
        self.confirming=False
        if value==self.power_sources.get('approx' if approx else 'exact'):
            self.status.set(f'전투력 변화 없음: {value:,} ({info})');return
        previous_same_mode=self.power_sources.get('approx' if approx else 'exact')
        if previous_same_mode is not None and (value>previous_same_mode*1.30 or value<previous_same_mode*0.70):
            self.status.set(f'전투력 {value:,} · 이전 {previous_same_mode:,} 대비 변화가 너무 커서 저장 보류. 영역 확인 필요!')
            return
        if previous_same_mode is None and self.last_power is not None and (value>self.last_power*1.30 or value<self.last_power*0.70):
            self.status.set(f'전투력 {value:,} · 이전 기록과 크게 달라서 저장 보류. 수동으로 정보창을 재확인해 줘.')
            return
        # Different source accuracy (approx/exact) can differ by a few points.
        delta=value-previous_same_mode if previous_same_mode is not None else None
        row={'timestamp':now_iso(),'combat_power':value,'change':'' if delta is None else delta,
             'source':'screen_ocr_K_approx' if approx else 'screen_ocr_exact_display'}
        try:append_rows(POWER_LOG,['timestamp','combat_power','change','source'],[row])
        except OSError as e:self.status.set('전투력 파일 저장 오류: '+str(e));return
        self.last_power=value;self.last_power_approx=approx
        self.power_sources['approx' if approx else 'exact']=value
        self.power_label.set(self.describe_power())
        self.status.set(f'전투력 기록 저장: {value:,} ({info}), 변화량 {delta if delta is not None else "첫 기록"}')
        self.add_recent(f'{datetime.now():%H:%M:%S}  전투력 {value:,}'+(f' ({delta:+,})' if delta is not None else ' (첫 기록)')+(' [약]' if approx else ' [정확]'))

    def review_stats(self,section,results):
        win=tk.Toplevel(self.root);win.title(f'{section} 상세 인식 결과 · 확인 후 저장')
        win.geometry('790x740');win.minsize(660,520)
        ttk.Label(win,text=f'{section} 상세 능력치 · 숫자를 확인하고 필요한 칸만 수정해 줘',style='Title.TLabel').pack(anchor='w',padx=15,pady=(12,6))
        ttk.Label(win,text='노란 안내 표시(⚠)는 OCR 두 번의 결과가 다르거나 읽지 못한 항목이야. 잘못 읽힌 칸을 직접 수정할 수 있어.',wraplength=740).pack(anchor='w',padx=15,pady=(0,5))
        outer=ttk.Frame(win);outer.pack(fill='both',expand=True,padx=15,pady=8)
        canvas=tk.Canvas(outer,highlightthickness=0)
        sc=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=sc.set)
        sc.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        inside=ttk.Frame(canvas)
        canvas.create_window((0,0),window=inside,anchor='nw')
        inside.bind('<Configure>',lambda _:canvas.configure(scrollregion=canvas.bbox('all')))
        for col,name in enumerate(['능력치','인식된 수치','이전 기록','인식 상태']):
            ttk.Label(inside,text=name).grid(row=0,column=col,padx=8,pady=5,sticky='w')
        boxes=[]
        for idx,item in enumerate(results,start=1):
            ttk.Label(inside,text=item['name']).grid(row=idx,column=0,padx=8,pady=6,sticky='w')
            rawvalue='' if item['value'] is None else as_text_value(item['value'],item['unit'])
            var=tk.StringVar(value=rawvalue)
            ttk.Entry(inside,textvariable=var,width=16).grid(row=idx,column=1,padx=8,pady=5,sticky='w')
            previous=self.stat_cache.get(f'{section}|{item["name"]}')
            ttk.Label(inside,text='—' if previous is None else as_text_value(previous,item['unit'])).grid(row=idx,column=2,padx=8,pady=5,sticky='w')
            uncertainty='⚠ 확인 필요' if item['uncertain'] or item['value'] is None else '✓'
            ttk.Label(inside,text=uncertainty).grid(row=idx,column=3,padx=8,pady=5,sticky='w')
            boxes.append((item,var))
        bottom=ttk.Frame(win);bottom.pack(fill='x',padx=15,pady=10)
        def save():
            values=[]
            from ocr_utils import parse_stat
            for item,var in boxes:
                s=var.get().strip()
                if not s:
                    # Blanks remain unrecorded; don't erase prior data by mistake.
                    continue
                value=parse_stat(s,item['unit'])
                if value is None:
                    messagebox.showerror('수치 확인',f'{item["name"]}: 숫자 형식을 확인해 줘.\n입력값: {s}',parent=win)
                    return
                values.append((item['name'],item['unit'],value))
            if not values:
                messagebox.showerror('수치 확인','저장할 숫자가 하나도 없어.',parent=win);return
            if self.commit_stats(section,values):win.destroy()
        ttk.Button(bottom,text='확인한 수치 저장 (증가·감소 모두 기록)',command=save).pack(side='right',padx=5)
        ttk.Button(bottom,text='취소 · 저장하지 않기',command=win.destroy).pack(side='right',padx=5)

    def commit_stats(self,section,values):
        timestamp=now_iso();new=dict(self.stat_cache)
        changes=[]
        for name,unit,value in values:
            key=f'{section}|{name}'
            previous=new.get(key)
            if previous is not None and value==previous:continue
            change='' if previous is None else round(value-previous,3)
            changes.append({'timestamp':timestamp,'section':section,'name':name,
                            'value':value,'unit':unit,'previous':'' if previous is None else previous,
                            'change':change,'source':'screen_ocr_user_verified'})
            new[key]=value
        if not changes:
            self.status.set(f'{section} 상세 · 이전 기록과 동일해. 중복 저장하지 않았어.');return True
        fields=['timestamp','section','name','value','unit','previous','change','source']
        try:
            append_rows(STAT_LOG,fields,changes)
            snapshot={'timestamp':timestamp,'captured_section':section}
            for sec,name,unit in ALL_FIELDS:
                val=new.get(f'{sec}|{name}')
                snapshot[f'{sec}__{name}']='' if val is None else val
            append_rows(SNAP_LOG,list(snapshot.keys()),[snapshot])
            STAT_CACHE.write_text(json.dumps(new,ensure_ascii=False,indent=2),encoding='utf-8')
        except OSError as e:
            messagebox.showerror('기록 오류','파일 저장에 실패했어: '+str(e));return False
        self.stat_cache=new
        self.update_stats_display()
        self.status.set(f'{section} 상세 {len(changes)}개 변경 사항 저장됨 (증가·감소 모두 기록)')
        for item in changes:
            change=item['change']
            suffix='첫 기록' if change=='' else f'변화 {change:+g}{item["unit"] if item["unit"]=="%" else ""}'
            self.add_recent(f'{datetime.now():%H:%M:%S}  [{section}] {item["name"]}: {as_text_value(item["value"],item["unit"])} ({suffix})')
        return True

    def show_latest(self):
        win=tk.Toplevel(self.root);win.title('현재 저장된 상세 능력치');win.geometry('690x680')
        outer=ttk.Frame(win,padding=12);outer.pack(fill='both',expand=True)
        tree=ttk.Treeview(outer,columns=('section','name','value'),show='headings')
        for name,label,width in [('section','구분',75),('name','능력치',320),('value','최근 기록값',160)]:
            tree.heading(name,text=label);tree.column(name,width=width,stretch=(name=='name'))
        tree.pack(fill='both',expand=True)
        for section,name,unit in ALL_FIELDS:
            value=self.stat_cache.get(f'{section}|{name}')
            tree.insert('',tk.END,values=(section,name,'—' if value is None else as_text_value(value,unit)))
        ttk.Button(outer,text='닫기',command=win.destroy).pack(anchor='e',pady=8)

    def tick(self):
        while True:
            try:event=self.events.get_nowait()
            except queue.Empty:break
            if event=='toggle':self.toggle()
            elif event=='manual':self.measure_manual()
            elif isinstance(event,tuple):
                if event[0]=='error':
                    self.busy=False;self.status.set('인식 오류: '+str(event[1])[:180])
                elif event[0]=='warning':self.status.set(event[1])
                elif event[0]=='measured':
                    _,target,manual,result=event
                    self.busy=False
                    if target.startswith('전투력'):self.handle_power(result,manual,target)
                    else:
                        self.status.set(f'{target} 탭 인식 완료 · 내용을 확인하고 저장해 줘.')
                        self.review_stats(target,result)
        if self.active and not self.busy and time.monotonic()>=self.next_scan:
            self.next_scan=time.monotonic()+int(self.cfg['interval'])
            self.scan(self.cfg.get('auto_source','전투력(상세창)'),False)
        self.root.after(150,self.tick)

    def close(self):
        self.active=False
        try:self.listener.stop()
        except Exception:pass
        self.root.destroy()

if __name__=='__main__':
    root=tk.Tk()
    Tracker(root)
    root.mainloop()
