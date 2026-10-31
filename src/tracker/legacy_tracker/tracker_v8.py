"""도깨비의 세계 성장 기록기 v8: 전체화면 캡처 개선 및 진단.

v7 GUI/GIF + DXcam Desktop Duplication, and screenshot-file ROI fallback.
No game automation, memory reading, networking, or upload.
"""
import tkinter as tk
import json
import shutil
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from PIL import Image, ImageTk

from core_v5 import CONFIG
from gif_v7 import TrackerV7
from capture_v8 import DXCAM_LABEL, CaptureError, dxcam_capture, likely_black_fullscreen, screenshot_for_monitor

VERSION='v8'

class TrackerV8(TrackerV7):
    def __init__(self, root):
        # Override which DXcam output is used if DXGI and MSS monitor ordering differ.
        self.dxcam_output_var=tk.StringVar(master=root,value='자동')
        fresh=not CONFIG.exists()
        if fresh:
            # Only migrate preferences / image, NOT OCR records or CSV files.
            # A user's existing v7 theme and ROIs should carry forward when
            # v8 is extracted beside v7 in its own folder.
            prior=CONFIG.parent.parent/'dokkaebi_tracker_v7'
            prior_cfg=prior/'config.json'
            if prior_cfg.is_file():
                try:
                    prefs=json.loads(prior_cfg.read_text(encoding='utf-8'))
                    allowed={'interval','monitor_index','tesseract_path','font_size',
                             'region_power','region_power_detail','region_stats',
                             'auto_source','key_auto','mods_auto','key_now','mods_now',
                             'gif_speed','gif_playing'}
                    safe={key:value for key,value in prefs.items() if key in allowed}
                    safe['capture_method']=DXCAM_LABEL
                    CONFIG.write_text(json.dumps(safe,ensure_ascii=False,indent=2),encoding='utf-8')
                except (OSError,ValueError,TypeError):pass
            for filename in ('user_background.gif','user_background.png'):
                source=prior/'assets'/filename
                dest=CONFIG.parent/'assets'/filename
                if source.is_file() and not dest.exists():
                    try:
                        dest.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copyfile(source,dest)
                        break
                    except OSError:pass
        super().__init__(root)
        self.dxcam_output_var.set(str(self.cfg.get('dxcam_output_index','자동')))
        self.root.title('도깨비의 세계 · 전투력/상세 능력치 기록기 v8')
        self.banner.itemconfigure(self.banner_title,text='도깨비의 세계  |  성장 기록기 v8')
        self.banner.itemconfigure(self.banner_sub,text='전체화면 DXcam · GIF 배경 · 전투력·상세 능력치 기록')
        if fresh:
            self.cfg['capture_method']=DXCAM_LABEL
            self.capture_method.set(DXCAM_LABEL)
            self.save_settings()
        self.status.set('v8 준비! 기본 캡처는 DXcam이야. 먼저 전체화면 캡처 테스트를 해보자.')

    def make_ui(self):
        super().make_ui()
        # Append extra controls to the blue region-selection panel in the main tab.
        inner=self.main_scroller.winfo_children()[0]
        dashboard=inner.winfo_children()[1]
        left=dashboard.winfo_children()[0]
        region_card=left.winfo_children()[0]
        from ui_v6 import BLUE, CYAN, MUTED
        row=tk.Frame(region_card,bg=BLUE)
        row.pack(fill='x',padx=17,pady=(0,12))
        ttk.Button(row,text='🖥  전체화면 캡처 진단',command=self.test_capture,
                   style='Accent.TButton').pack(side='left',padx=(0,9))
        ttk.Button(row,text='📂  스크린샷 파일에서 영역 지정',command=self.choose_region_file,
                   style='Secondary.TButton').pack(side='left')
        self._label(region_card,'검은 화면이면: 설정에서 DXcam 선택 → 모니터 확인 → 캡처 진단.\n'
                  '스크린샷 파일은 영역 지정용이야. 실시간 자동 측정에는 정상적인 라이브 캡처가 필요해.',
                  BLUE,MUTED,wrap=800).pack(anchor='w',padx=18,pady=(0,12))
        # A concise explanation next to the capture method settings.
        settings_inner=self.settings_scroller.winfo_children()[0]
        settings_top=settings_inner.winfo_children()[1]
        screen_card=settings_top.winfo_children()[0]
        self._label(screen_card,'DXcam 출력 화면 번호 (듀얼 모니터일 때) ',
                    screen_card.cget('bg'),MUTED).pack(fill='x',padx=17,pady=(9,2))
        ttk.Combobox(screen_card,textvariable=self.dxcam_output_var,
                     values=['자동','0','1','2','3','4'],state='readonly').pack(fill='x',padx=17,pady=(0,8))
        self._label(screen_card,'DXcam은 전체화면 게임용. MSS와 ImageGrab은 대체 방식이야.\n'
                    'DXcam 사용 시 requirements.txt의 추가 설치가 필요해.',
                    screen_card.cget('bg'),MUTED,wrap=530).pack(fill='x',padx=17,pady=(0,14))

    def capture(self,region):
        if self.cfg.get('capture_method')==DXCAM_LABEL:
            i=int(self.cfg['monitor_index'])-1
            monitor=self.monitors[i]
            idx=self.cfg.get('dxcam_output_index','자동')
            if idx!='자동':
                idx=int(idx)
            else:idx=i
            return dxcam_capture(region,monitor,idx)
        return super().capture(region)

    def save_settings(self):
        self.cfg['dxcam_output_index']=self.dxcam_output_var.get()
        return super().save_settings()

    def test_capture(self):
        if self.busy:return
        if not self.save_settings():return
        self.status.set('3초 후 선택 모니터 화면을 캡처할게. 게임이 보이도록 전환해 줘.')
        self.root.iconify()
        self.root.after(3000,self._finish_capture_test)

    def _finish_capture_test(self):
        try:
            monitor=self.monitors[self.cfg['monitor_index']-1]
            im=self.capture(monitor)
            is_black=likely_black_fullscreen(im)
        except Exception as e:
            self.root.deiconify()
            messagebox.showerror('캡처 진단 실패',str(e),parent=self.root)
            self.status.set('캡처 실패. 설정의 DXcam/모니터를 확인해 줘.')
            return
        self.root.deiconify()
        # Preview the actual pixels rather than claiming capture success.
        win=tk.Toplevel(self.root)
        win.title('캡처 진단 · 실제 캡처된 화면')
        scale=min(1000/im.width,650/im.height,1)
        photo=ImageTk.PhotoImage(im.resize((max(1,round(im.width*scale)),max(1,round(im.height*scale)))))
        lab=tk.Label(win,image=photo)
        lab.image=photo
        lab.pack(padx=9,pady=8)
        msg=('⚠ 게임 영역이 거의 검게 캡처됐어. 다른 캡처 방식 또는 테두리 없는 창 모드를 시도해 줘.'
             if is_black else '✅ 화면 픽셀이 캡처됐어. 게임 장면이 보이는지 직접 확인하고 숫자 영역을 선택해 줘.')
        ttk.Label(win,text=msg,wraplength=980).pack(padx=14,pady=(2,12))
        self.status.set(msg)

    def show_selection(self):
        try:
            monitor=self.monitors[self.cfg['monitor_index']-1]
            image=self.capture(monitor)
            if likely_black_fullscreen(image):
                self.root.deiconify()
                self.status.set('검은 화면 감지! 선택하지 말고 캡처 방식을 DXcam으로 바꿔 봐.')
                messagebox.showwarning('검은 화면 감지',
                    '캡처 화면에 게임이 보이지 않아. 잘못된 숫자 위치를 저장하지 않도록 선택을 중단했어.\n\n'
                    '1. 설정에서 캡처 방식을 DXcam (게임 전체화면)으로 선택\n'
                    '2. 캡처 모니터를 게임이 실행 중인 화면으로 선택\n'
                    '3. 듀얼 모니터면 DXcam 출력 화면 번호 0/1을 바꿔 테스트\n'
                    '4. 캡처 진단을 다시 실행\n'
                    '5. 그래도 실패하면 테두리 없는 창 모드를 사용하거나 스크린샷 파일로 영역을 지정해 줘.',
                    parent=self.root)
                return
        except Exception as e:
            self.root.deiconify()
            messagebox.showerror('게임 화면 캡처 오류',str(e),parent=self.root)
            return
        self.root.deiconify()
        self._show_selection_image(image,monitor)

    def choose_region_file(self):
        if self.busy:return
        if not self.save_settings():return
        file=filedialog.askopenfilename(parent=self.root,title='전체 게임 화면 스크린샷 선택',
              filetypes=[('스크린샷','*.png *.jpg *.jpeg *.bmp *.webp'),('모든 파일','*.*')])
        if not file:return
        try:
            monitor=self.monitors[self.cfg['monitor_index']-1]
            with Image.open(file) as f:im=screenshot_for_monitor(f,monitor,self.monitors)
            if likely_black_fullscreen(im):
                raise CaptureError('선택한 스크린샷이 검은 화면이야. 게임이 보이는 스크린샷을 선택해 줘.')
        except Exception as e:
            messagebox.showerror('스크린샷 읽기 실패',str(e),parent=self.root)
            return
        self.status.set('파일에서 화면을 불러왔어. 정확한 전투력 숫자만 드래그해 줘. 실시간 캡처는 별도 테스트가 필요해.')
        self._show_selection_image(im,monitor)

if __name__=='__main__':
    root=tk.Tk()
    TrackerV8(root)
    root.mainloop()
