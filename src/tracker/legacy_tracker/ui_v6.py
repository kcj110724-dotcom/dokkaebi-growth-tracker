"""도깨비의 세계 전투력·상세 능력치 기록기 v6 — 시각 개편판.

캡처/OCR/CSV 기록 로직은 이전 v5 코드를 보존하고, v6에서는 UI만 재설계함.
게임 파일·메모리 접근이나 게임 조작 자동화 없음. 스크린샷은 사용자가 제공.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import shutil
import os
from PIL import Image, ImageTk

from core_v5 import (Tracker as V5Tracker, APP_NAME as OLD_NAME,
                     MOD_OPTIONS, KEY_NAMES, chord, STATS, ALL_FIELDS,
                     as_text_value)

HERE=Path(__file__).resolve().parent
USER_ASSETS = Path(os.environ.get('DOKKAEBI_ASSETS_DIR', str(HERE/'assets'))).resolve()
USER_ASSETS.mkdir(parents=True,exist_ok=True)
DEFAULT_BG = (USER_ASSETS/'fixed_background.png' if (USER_ASSETS/'fixed_background.png').exists() else HERE/'assets'/'fantasy_background.jpg')
APP_TITLE='도깨비의 세계 · 전투력/상세 능력치 기록기 v6'
BG='#080D2B'
NAVY='#10183E'
PANEL='#101C46'
BLUE='#132B53'
PURPLE='#211A54'
GREEN='#123F4D'
AMBER='#3C254B'
TEXT='#F3F0FF'
MUTED='#B5C1EB'
GOLD='#FFD78A'
CYAN='#90DFFF'
VIOLET='#D6AFFF'
MINT='#89F0D4'
BORDER='#665DA7'

class TrackerV6(V5Tracker):
    def __init__(self,root):
        self._hotkey_ready=False
        # Never use gameplay screenshots as the default UI background.
        # Users can import an image they own into the program's assets folder.
        self._theme_image_path = USER_ASSETS/'user_background.png'
        if not self._theme_image_path.exists():
            self._theme_image_path = DEFAULT_BG
        self._load_theme_images()
        self._banner_photo=None
        self._wall_photo=None
        self._banner_w=0
        super().__init__(root)
        root.title('도깨비의 세계 · 성장 기록기 측정 센터 v0.0.1')
        root.geometry('1380x900')
        root.minsize(1080,725)
        self._hotkey_ready=True
        self._hotkey_last_valid=(self.mod_auto.get(),self.key_auto.get(),self.mod_now.get(),self.key_now.get())
        self._apply_hotkey_ui()
        self._refresh_state()
        self.status.set('v6 준비 완료 · 캐릭터 정보창의 전투력을 정확하게 기록해 봐!')

    def make_ui(self):
        self.root.configure(bg=BG)
        self._install_styles()
        # Decorative background is user-selectable; opaque cards preserve readability.
        self.wall=tk.Label(self.root,bd=0,highlightthickness=0,bg=BG)
        self.wall.place(x=0,y=0,relwidth=1,relheight=1)
        self.wall.lower()
        self._background_after=None
        self.root.bind('<Configure>',self._schedule_wallpaper,add='+')
        self.shell=tk.Frame(self.root,bg=BG,highlightthickness=1,highlightbackground='#7666C7')
        self.shell.pack(fill='both',expand=True,padx=19,pady=15)

        self.banner=tk.Canvas(self.shell,height=182,bg=NAVY,highlightthickness=0)
        self.banner.pack(fill='x')
        self.banner.bind('<Configure>',self._render_banner,add='+')
        self.banner_title=self.banner.create_text(30,64,anchor='w',text='도깨비의 세계  |  성장 기록기 v6',
                          fill='#fff4da',font=('맑은 고딕',24,'bold'))
        self.banner_sub=self.banner.create_text(32,109,anchor='w',text='정확 전투력 · 상세 능력치 24종 · 자동 기록',
                         fill='#e6edff',font=('맑은 고딕',13,'bold'))

        self.status_panel=tk.Frame(self.shell,bg='#131E48',padx=19,pady=12)
        self.status_panel.pack(fill='x')
        self.status_label=tk.Label(self.status_panel,textvariable=self.status,bg='#131E48',fg=CYAN,
                                    anchor='w',justify='left',wraplength=1150)
        self.status_label.pack(fill='x')

        self.tabs=ttk.Notebook(self.shell,style='Theme.TNotebook')
        self.tabs.pack(fill='both',expand=True,padx=15,pady=(12,15))
        main_host=tk.Frame(self.tabs,bg=BG)
        settings_host=tk.Frame(self.tabs,bg=BG)
        self.tabs.add(main_host,text='  ⚔  측정 및 기록  ')
        self.tabs.add(settings_host,text='  ⚙  설정 · 글씨 · 단축키  ')
        main,self.main_scroller=self._scrollable_tab(main_host)
        settings,self.settings_scroller=self._scrollable_tab(settings_host)
        self.root.bind_all('<MouseWheel>',self._on_mousewheel,add='+')

        # MEASURE PAGE ----------------------------------------------------
        summary=tk.Frame(main,bg=BG)
        summary.pack(fill='x',pady=(0,11))
        power_kpi=self._kpi(summary,'최근 전투력',self.power_label,GOLD)
        power_kpi.pack(side='left',fill='x',expand=True,padx=(0,8))
        self.stat_summary=tk.StringVar(value='상세 능력치: 0/24개 기록됨')
        stat_kpi=self._kpi(summary,'상세 능력치',self.stat_summary,VIOLET)
        stat_kpi.pack(side='left',fill='x',expand=True,padx=(0,8))
        self.auto_state=tk.StringVar(value='대기 중 · 자동 감시 꺼짐')
        auto_kpi=self._kpi(summary,'자동 측정 상태',self.auto_state,MINT)
        auto_kpi.pack(side='left',fill='x',expand=True)

        dashboard=tk.Frame(main,bg=BG)
        dashboard.pack(fill='both',expand=True)
        dashboard.grid_columnconfigure(0,weight=6,uniform='cols')
        dashboard.grid_columnconfigure(1,weight=4,uniform='cols')
        dashboard.grid_rowconfigure(0,weight=1)
        left=tk.Frame(dashboard,bg=BG)
        left.grid(row=0,column=0,sticky='nsew',padx=(0,9))
        right=tk.Frame(dashboard,bg=BG)
        right.grid(row=0,column=1,sticky='nsew',padx=(9,0))

        region_card=self._card(left,'01  화면 영역 지정','정확한 숫자를 읽을 위치를 선택해 줘',BLUE,CYAN)
        region_card.pack(fill='x',pady=(0,14))
        region_row=tk.Frame(region_card,bg=BLUE)
        region_row.pack(fill='x',padx=17,pady=(10,6))
        self._label(region_row,'선택할 영역',BLUE).pack(side='left',padx=(0,12))
        ttk.Combobox(region_row,textvariable=self.region_target,
                     values=['전투력(상세창)','전투력(HUD)','상세 수치 열'],state='readonly',width=17).pack(side='left',padx=(0,9))
        ttk.Button(region_row,text='5초 후 화면 캡처 · 드래그 선택',command=self.choose_region,
                   style='Accent.TButton').pack(side='left',fill='x',expand=True)
        self._label(region_card,'영역 저장 현황',BLUE,CYAN,weight='bold').pack(anchor='w',padx=18,pady=(7,3))
        self._label(region_card,'',BLUE,textvar=self.region_label,wrap=650).pack(anchor='w',fill='x',padx=18,pady=(0,10))
        self._hint(region_card,'정확 전투력 → 캐릭터 정보창 왼쪽 위 주황색 숫자만 선택\n상세 능력치 → 방어 탭 오른쪽 숫자 10줄을 세로로 선택',BLUE)

        scan_card=self._card(left,'02  측정 실행','게임은 끄지 않고, 화면에 보이는 숫자만 읽어',GREEN,MINT)
        scan_card.pack(fill='x')
        target_row=tk.Frame(scan_card,bg=GREEN)
        target_row.pack(fill='x',padx=17,pady=(12,10))
        self._label(target_row,'수동 측정 화면',GREEN).pack(side='left',padx=(0,12))
        ttk.Combobox(target_row,textvariable=self.measure_target,
                     values=['전투력(상세창)','전투력(HUD)','공격','방어','기타'],
                     state='readonly',width=18).pack(side='left',fill='x',expand=True)
        buttons=tk.Frame(scan_card,bg=GREEN)
        buttons.pack(fill='x',padx=17,pady=(0,12))
        self.now_btn=ttk.Button(buttons,textvariable=self.button_now_text,command=self.measure_manual,
                                style='Primary.TButton')
        self.now_btn.pack(side='left',fill='x',expand=True,padx=(0,8))
        self.auto_btn=ttk.Button(buttons,textvariable=self.button_auto_text,command=self.toggle,
                                 style='Primary.TButton')
        self.auto_btn.pack(side='left',fill='x',expand=True)
        auto_row=tk.Frame(scan_card,bg=GREEN)
        auto_row.pack(fill='x',padx=17,pady=(0,12))
        self._label(auto_row,'자동 측정 대상',GREEN).pack(side='left',padx=(0,12))
        ttk.Combobox(auto_row,textvariable=self.auto_source,values=['전투력(상세창)','전투력(HUD)'],
                     state='readonly',width=19).pack(side='left')
        self._hint(scan_card,'정보창이 닫혀 있으면 정확 전투력 측정을 건너뛰어.\n상세 능력치 24개는 게임에서 공격·방어·기타 탭을 열고 수동 측정해야 해.',GREEN)

        record_card=self._card(right,'03  최근 기록','변경된 값만 저장 · 파일은 내 컴퓨터에 남아',PURPLE,VIOLET)
        record_card.pack(fill='both',expand=True)
        top=tk.Frame(record_card,bg=PURPLE)
        top.pack(fill='x',padx=16,pady=(10,9))
        self._label(top,'전투력과 능력치 변화 내역',PURPLE).pack(side='left')
        ttk.Button(top,text='📂 기록 폴더',style='Small.TButton',command=self.open_folder).pack(side='right')
        record_box=tk.Frame(record_card,bg=PURPLE)
        record_box.pack(fill='both',expand=True,padx=16,pady=(0,11))
        self.recent=tk.Listbox(record_box,height=10,activestyle='none',selectbackground='#5747B5',
                               background='#0E143A',foreground='#F3F0FF',
                               highlightthickness=0,relief='flat',bd=0)
        self.recent.pack(side='left',fill='both',expand=True)
        bar=ttk.Scrollbar(record_box,orient='vertical',command=self.recent.yview)
        bar.pack(side='right',fill='y')
        self.recent.configure(yscrollcommand=bar.set)
        self.add_recent('기록 없음 · 측정을 시작해 봐!')
        ttk.Button(record_card,text='상세 능력치 24개 보기',command=self.show_latest,
                   style='Secondary.TButton').pack(fill='x',padx=16,pady=(0,13))

        # SETTINGS PAGE ----------------------------------------------------
        image_card=self._card(settings,'00  프로그램 배경 이미지','게임 장면 대신 원하는 일러스트 또는 참고 이미지를 바로 적용해',NAVY,GOLD)
        image_card.pack(fill='x',pady=(0,13))
        image_actions=tk.Frame(image_card,bg=NAVY)
        image_actions.pack(fill='x',padx=17,pady=(12,7))
        ttk.Button(image_actions,text='🖼  배경 이미지 불러오기',command=self.select_theme_image,
                   style='Accent.TButton').pack(side='left',padx=(0,9))
        ttk.Button(image_actions,text='기본 배경으로 되돌리기',command=self.reset_theme_image,
                   style='Secondary.TButton').pack(side='left')
        self.theme_image_label=tk.StringVar(value=self._theme_label())
        self._label(image_card,'',NAVY,MUTED,textvar=self.theme_image_label,wrap=960).pack(fill='x',padx=17,pady=(3,12))

        settings_top=tk.Frame(settings,bg=BG)
        settings_top.pack(fill='x',pady=(0,12))
        screen_card=self._card(settings_top,'01  화면 · OCR 설정','게임을 캡처할 모니터와 숫자 인식 엔진',BLUE,CYAN)
        screen_card.pack(side='left',fill='both',expand=True,padx=(0,8))
        fontsize_card=self._card(settings_top,'02  글씨 크기','전체 메뉴·버튼·기록창에 반영',PURPLE,VIOLET)
        fontsize_card.pack(side='left',fill='both',expand=True,padx=(8,0))
        for label,widget in [
            ('캡처할 모니터',ttk.Combobox(screen_card,textvariable=self.monitor_var,
                       values=self.monitors_label,state='readonly')),
            ('캡처 방식',ttk.Combobox(screen_card,textvariable=self.capture_method,
                       values=['DXcam (게임 전체화면)','MSS','ImageGrab'],state='readonly')),
            ('Tesseract 실행 파일 경로',ttk.Entry(screen_card,textvariable=self.tess_var)),
            ('자동 측정 간격 (초)',ttk.Spinbox(screen_card,textvariable=self.interval_var,
                       from_=5,to=3600,width=10))]:
            self._label(screen_card,label,BLUE).pack(anchor='w',padx=17,pady=(11,3))
            widget.pack(fill='x',padx=17,pady=(0,4))
        tk.Frame(screen_card,bg=BLUE,height=12).pack()
        self._label(fontsize_card,'프로그램 전체 글씨 크기',PURPLE).pack(anchor='w',padx=17,pady=(14,8))
        adjust=tk.Frame(fontsize_card,bg=PURPLE)
        adjust.pack(fill='x',padx=17)
        ttk.Spinbox(adjust,textvariable=self.font_var,from_=10,to=26,width=6).pack(side='left')
        self._label(adjust,'pt   (10~26)',PURPLE).pack(side='left',padx=(10,0))
        ttk.Button(fontsize_card,text='글씨 크기 바로 적용',command=self.apply_font_from_ui,
                   style='Accent.TButton').pack(anchor='w',padx=17,pady=(17,12))
        self._label(fontsize_card,'구분 제목, 안내, 버튼, 입력창, 기록 목록까지\n함께 확대돼. 창 크기도 자유롭게 늘릴 수 있어.',PURPLE,wrap=440).pack(anchor='w',padx=17,pady=(0,10))

        hot_card=self._card(settings,'03  단축키 자유 지정','설정하는 즉시 ‘측정 및 기록’ 버튼의 키 표시와 실제 단축키가 함께 바뀌어',AMBER,GOLD)
        hot_card.pack(fill='x')
        colheaders=tk.Frame(hot_card,bg=AMBER)
        colheaders.pack(fill='x',padx=19,pady=(10,0))
        self._label(colheaders,'기능',AMBER,GOLD,weight='bold',width=22).grid(row=0,column=0,sticky='w')
        self._label(colheaders,'조합 키',AMBER,GOLD,weight='bold',width=18).grid(row=0,column=1,sticky='w',padx=9)
        self._label(colheaders,'기본 키',AMBER,GOLD,weight='bold',width=19).grid(row=0,column=2,sticky='w',padx=9)
        chooser=tk.Frame(hot_card,bg=AMBER)
        chooser.pack(fill='x',padx=19,pady=(4,7))
        self.hotkey_controls=[]
        for rownum,(title,mod,key) in enumerate([
            ('자동 측정 시작 / 중지',self.mod_auto,self.key_auto),
            ('지금 측정',self.mod_now,self.key_now)]):
            self._label(chooser,title,AMBER,width=22).grid(row=rownum,column=0,sticky='w',pady=5)
            md=ttk.Combobox(chooser,textvariable=mod,values=MOD_OPTIONS,state='readonly',width=18)
            md.grid(row=rownum,column=1,padx=9,pady=5,sticky='w')
            ky=ttk.Combobox(chooser,textvariable=key,values=KEY_NAMES,state='readonly',width=19)
            ky.grid(row=rownum,column=2,padx=9,pady=5,sticky='w')
            md.bind('<<ComboboxSelected>>',self._on_hotkey_changed)
            ky.bind('<<ComboboxSelected>>',self._on_hotkey_changed)
            self.hotkey_controls.extend([md,ky])
        self.hotkey_preview=tk.StringVar(value='')
        self._label(hot_card,'',AMBER,MINT,weight='bold',textvar=self.hotkey_preview,wrap=950).pack(anchor='w',padx=20,pady=(3,5))
        self._hint(hot_card,'서로 같은 키는 지정할 수 없어. Windows 예약 키는 제한될 수 있고, 게임 조작키와 겹치지 않게 설정하는 걸 추천해.',AMBER)
        foot=tk.Frame(settings,bg=BG)
        foot.pack(fill='x',pady=(14,0))
        self._label(foot,'설정은 파일에 저장되며 다음 실행 때도 유지돼.',BG,MUTED).pack(side='left')
        ttk.Button(foot,text='💾  모든 설정 저장',command=self.save_settings,
                   style='Accent.TButton').pack(side='right')

    def _scrollable_tab(self,host):
        # Large fonts must never hide lower controls: both tabs scroll vertically.
        canvas=tk.Canvas(host,background=BG,borderwidth=0,highlightthickness=0)
        sb=ttk.Scrollbar(host,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side='right',fill='y')
        canvas.pack(side='left',fill='both',expand=True)
        inner=tk.Frame(canvas,bg=BG,padx=4,pady=8)
        winid=canvas.create_window((0,0),window=inner,anchor='nw')
        inner.bind('<Configure>',lambda ev:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda ev:canvas.itemconfigure(winid,width=ev.width))
        return inner,canvas

    def _on_mousewheel(self,event):
        try:
            if isinstance(event.widget,(tk.Listbox,ttk.Combobox,ttk.Spinbox)):return
            if event.widget.winfo_toplevel()!=self.root:return
            scroller=self.main_scroller if self.tabs.index(self.tabs.select())==0 else self.settings_scroller
            scroller.yview_scroll(-1 if event.delta>0 else 1,'units')
        except (tk.TclError,AttributeError):pass

    def _install_styles(self):
        style=ttk.Style(self.root)
        try:style.theme_use('clam')
        except tk.TclError:pass
        style.configure('.',background=BG,foreground=TEXT)
        style.configure('TLabel',background=BG,foreground=TEXT)
        style.configure('TFrame',background=BG)
        style.configure('Theme.TNotebook',background=BG,borderwidth=0,tabmargins=(0,5,0,0))
        style.configure('TNotebook.Tab',background='#1A224E',foreground='#DDE7FF',padding=(24,13))
        style.map('TNotebook.Tab',background=[('selected','#49369B'),('active','#303973')],
                  foreground=[('selected','#FFFFFF')])
        style.configure('TButton',background='#29366F',foreground=TEXT,padding=(14,10),borderwidth=1)
        style.map('TButton',background=[('active','#4254A5'),('pressed','#302B83')])
        style.configure('Accent.TButton',background='#6244AA',foreground='#FFFFFF')
        style.map('Accent.TButton',background=[('active','#785BD0'),('pressed','#51369E')])
        style.configure('Primary.TButton',background='#254F91',foreground='#F2FCFF')
        style.map('Primary.TButton',background=[('active','#327BC5')])
        style.configure('Secondary.TButton',background='#403579',foreground=TEXT)
        style.map('Secondary.TButton',background=[('active','#6755AF')])
        style.configure('Small.TButton',background='#403579',foreground=TEXT,padding=(8,5))
        style.configure('TCombobox',fieldbackground='#eef4ff',background='#d0d9e9',foreground='#10213a',
                        selectbackground='#b9cbed',selectforeground='#10213a',arrowsize=17)
        style.map('TCombobox',fieldbackground=[('readonly','#e1eaf9')],foreground=[('readonly','#10213a')])
        style.configure('TEntry',fieldbackground='#eef4ff',foreground='#10213a')
        style.configure('TSpinbox',fieldbackground='#eef4ff',foreground='#10213a',background='#d0d9e9')
        style.configure('TScrollbar',background='#726BC6',troughcolor='#11183F')
        style.configure('Treeview',background='#10183E',fieldbackground='#10183E',foreground=TEXT,rowheight=28)
        style.configure('Treeview.Heading',background=BLUE,foreground=GOLD)
        self.ttkstyle=style

    def _label(self,parent,text,bg,fg=TEXT,weight='normal',wrap=0,width=None,textvar=None):
        opts={'bg':bg,'fg':fg,'anchor':'w','justify':'left',
              'font':('맑은 고딕',13,weight)}
        if wrap:opts['wraplength']=wrap
        if width:opts['width']=width
        if textvar is not None:opts['textvariable']=textvar
        else:opts['text']=text
        return tk.Label(parent,**opts)

    def _hint(self,parent,text,bg):
        self._label(parent,text,bg,MUTED,wrap=660).pack(anchor='w',fill='x',padx=18,pady=(2,15))

    def _card(self,parent,title,subtitle,bg,accent):
        panel=tk.Frame(parent,bg=bg,highlightbackground=BORDER,highlightthickness=1)
        tk.Frame(panel,bg=accent,height=4).pack(fill='x')
        heading=tk.Frame(panel,bg=bg)
        heading.pack(fill='x',padx=16,pady=(12,0))
        self._label(heading,title,bg,accent,weight='bold').pack(anchor='w')
        self._label(heading,subtitle,bg,MUTED,wrap=720).pack(anchor='w',pady=(3,0))
        return panel

    def _kpi(self,parent,title,var,accent):
        box=tk.Frame(parent,bg=NAVY,highlightbackground='#334660',highlightthickness=1,padx=13,pady=10)
        tk.Frame(box,bg=accent,height=3).pack(fill='x')
        self._label(box,title,NAVY,MUTED).pack(anchor='w',pady=(5,2))
        self._label(box,'',NAVY,accent,weight='bold',textvar=var).pack(anchor='w')
        return box

    def _load_theme_images(self):
        src=Image.open(self._theme_image_path).convert('RGB')
        self._wallpaper_src=src
        self._game_banner_src=src.copy()

    def _theme_label(self):
        if (USER_ASSETS/'user_background.png').exists():
            return '사용자 지정 이미지 적용 중 · 프로그램을 다시 실행해도 유지돼.'
        return '기본 판타지 테마 · 배경을 바꾸려면 위 버튼을 눌러 이미지 파일을 선택해.'

    def _reload_theme(self):
        self._load_theme_images()
        self._banner_w=0
        self._render_banner(type('Resize',(),{'width':self.banner.winfo_width()})())
        self._render_wallpaper()
        if hasattr(self,'theme_image_label'):
            self.theme_image_label.set(self._theme_label())

    def select_theme_image(self):
        selected=filedialog.askopenfilename(
            parent=self.root,title='프로그램 배경으로 사용할 이미지 선택',
            filetypes=[('이미지 파일','*.png *.jpg *.jpeg *.webp *.bmp'),('모든 파일','*.*')])
        if not selected:return
        try:
            src=Image.open(selected).convert('RGB')
            if src.width<300 or src.height<200:
                messagebox.showwarning('배경 이미지','너무 작은 이미지야. 가로 300px 이상을 추천해.')
            out=USER_ASSETS/'user_background.png'
            temp=USER_ASSETS/'user_background.new.png'
            # Reasonably cap enormous sources while preserving aspect ratio.
            src.thumbnail((2560,1440),Image.Resampling.LANCZOS)
            src.save(temp,optimize=True)
            temp.replace(out)
            self._theme_image_path=out
            self._reload_theme()
            self.status.set('새 배경 이미지를 적용했어! 재실행해도 유지돼.')
        except Exception as e:
            messagebox.showerror('이미지 적용 실패',str(e))

    def reset_theme_image(self):
        file=USER_ASSETS/'user_background.png'
        try:
            if file.exists():file.unlink()
            self._theme_image_path=DEFAULT_BG
            self._reload_theme()
            self.status.set('기본 판타지 테마로 되돌렸어.')
        except Exception as e:
            messagebox.showerror('배경 변경 실패',str(e))

    def _cover_crop(self,src,w,h):
        # Preserve aspect ratio for both landscape and portrait backgrounds.
        iw,ih=src.size
        ratio=max(w/iw,h/ih)
        nw,nh=max(1,round(iw*ratio)),max(1,round(ih*ratio))
        resized=src.resize((nw,nh),Image.Resampling.LANCZOS)
        x=(nw-w)//2;y=(nh-h)//2
        return resized.crop((x,y,x+w,y+h))

    def _schedule_wallpaper(self,event):
        if event.widget is not self.root:return
        if self._background_after is not None:
            try:self.root.after_cancel(self._background_after)
            except tk.TclError:pass
        self._background_after=self.root.after(140,self._render_wallpaper)

    def _render_wallpaper(self):
        self._background_after=None
        if not self.wall.winfo_exists():return
        w=max(1,self.root.winfo_width());h=max(1,self.root.winfo_height())
        if w<100 or h<100:return
        resized=self._cover_crop(self._wallpaper_src,w,h)
        self._wall_photo=ImageTk.PhotoImage(resized)
        self.wall.configure(image=self._wall_photo)
        self.wall.lower()

    def _render_banner(self,event):
        w=event.width
        if w<20 or abs(w-self._banner_w)<5:return
        self._banner_w=w
        art=self._cover_crop(self._game_banner_src,max(1,w),170)
        # Make text readable no matter how bright the imported reference image is.
        shade=Image.new('RGB',art.size,'#101627')
        art=Image.blend(art,shade,.48)
        photo=ImageTk.PhotoImage(art)
        self._banner_photo=photo
        # Recreate just the image, keeping title and subtitle above it.
        self.banner.delete('photo')
        self.banner.create_image(0,0,anchor='nw',image=photo,tags='photo')
        self.banner.tag_lower('photo')

    def _apply_hotkey_ui(self):
        am=chord(self.key_auto.get(),[] if self.mod_auto.get()=='없음' else self.mod_auto.get().split('+'))
        nw=chord(self.key_now.get(),[] if self.mod_now.get()=='없음' else self.mod_now.get().split('+'))
        self.button_auto_text.set(f'{am}  |  자동 시작 / 중지')
        self.button_now_text.set(f'{nw}  |  지금 측정')
        if hasattr(self,'hotkey_preview'):
            self.hotkey_preview.set(f'현재 단축키:  자동 측정 {am}    ·    지금 측정 {nw}')

    def update_hotkey_labels(self):
        self._apply_hotkey_ui()

    def _on_hotkey_changed(self,_event=None):
        if not self._hotkey_ready:return
        am=chord(self.key_auto.get(),[] if self.mod_auto.get()=='없음' else self.mod_auto.get().split('+'))
        nw=chord(self.key_now.get(),[] if self.mod_now.get()=='없음' else self.mod_now.get().split('+'))
        from core_v5 import KEY_NAMES
        if am==nw or am in {'Alt+F4','Alt+Tab','Ctrl+Alt+Delete','Ctrl+Shift+Escape'} or nw in {'Alt+F4','Alt+Tab','Ctrl+Alt+Delete','Ctrl+Shift+Escape'}:
            previous=self._hotkey_last_valid
            self.mod_auto.set(previous[0]);self.key_auto.set(previous[1]);self.mod_now.set(previous[2]);self.key_now.set(previous[3])
            self.status.set('단축키 충돌 또는 Windows 예약 키라서 변경을 취소했어. 다른 키를 골라줘.')
            return
        if self.save_settings():
            self._hotkey_last_valid=(self.mod_auto.get(),self.key_auto.get(),self.mod_now.get(),self.key_now.get())
            self.status.set(f'단축키 즉시 적용 완료!   자동 {am}  /  즉시 측정 {nw}')

    def save_settings(self):
        saved=super().save_settings()
        if saved:
            self._apply_hotkey_ui()
            if self._hotkey_ready:
                self._hotkey_last_valid=(self.mod_auto.get(),self.key_auto.get(),self.mod_now.get(),self.key_now.get())
        return saved

    def apply_font(self,size):
        try:size=int(size)
        except (TypeError,ValueError):size=14
        if not 10<=size<=26:
            messagebox.showwarning('글씨 크기','글씨는 10~26pt 사이에서 조절해 줘.');return
        import tkinter.font as tkfont
        for name in ('TkDefaultFont','TkTextFont','TkHeadingFont','TkMenuFont','TkCaptionFont','TkSmallCaptionFont','TkFixedFont'):
            try:tkfont.nametofont(name).configure(family='맑은 고딕',size=size)
            except tk.TclError:pass
        self.ttkstyle.configure('.',font=('맑은 고딕',size))
        self.ttkstyle.configure('TButton',font=('맑은 고딕',size,'bold'),padding=(12,max(5,size//3)))
        self.ttkstyle.configure('Accent.TButton',font=('맑은 고딕',size,'bold'))
        self.ttkstyle.configure('Primary.TButton',font=('맑은 고딕',size,'bold'))
        self.ttkstyle.configure('Small.TButton',font=('맑은 고딕',max(10,size-2)))
        self.ttkstyle.configure('TNotebook.Tab',font=('맑은 고딕',size,'bold'),padding=(16,max(7,size//2)))
        self.ttkstyle.configure('Treeview',font=('맑은 고딕',size),rowheight=size*2+7)
        self.ttkstyle.configure('Treeview.Heading',font=('맑은 고딕',size,'bold'))
        self.ttkstyle.configure('TCombobox',font=('맑은 고딕',size))
        self.ttkstyle.configure('TEntry',font=('맑은 고딕',size))
        self.ttkstyle.configure('TSpinbox',font=('맑은 고딕',size))
        # Tk labels/listbox have explicit fonts and must be updated independently.
        def visit(widget):
            if isinstance(widget,tk.Label):
                f=widget.cget('font')
                bold='bold' if 'bold' in str(f).lower() else 'normal'
                widget.configure(font=('맑은 고딕',size,bold))
                if int(widget.cget('wraplength') or 0):widget.configure(wraplength=max(300,min(1050,55*size)))
            elif isinstance(widget,tk.Listbox):
                widget.configure(font=('맑은 고딕',size))
            for child in widget.winfo_children():visit(child)
        visit(self.root)
        self.banner.itemconfigure(self.banner_title,font=('맑은 고딕',size+10,'bold'))
        self.banner.itemconfigure(self.banner_sub,font=('맑은 고딕',size,'bold'))
        self.cfg['font_size']=size
        if size>18:
            self.root.geometry(f'{min(self.root.winfo_screenwidth()-60,1380+(size-18)*36)}x{min(self.root.winfo_screenheight()-75,900+(size-18)*15)}')

    def toggle(self):
        super().toggle()
        self._refresh_state()

    def _refresh_state(self):
        if hasattr(self,'auto_state'):
            self.auto_state.set('동작 중 · 자동 감시 켜짐' if self.active else '대기 중 · 자동 감시 꺼짐')


if __name__=='__main__':
    window=tk.Tk()
    TrackerV6(window)
    window.mainloop()
