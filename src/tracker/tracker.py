"""도깨비의 세계 성장 기록기 v0 대시보드.

Read-only overview of the real CSV / JSON files written by the v8 OCR recorder.
The user explicitly opens the OCR tool for new captures: no fictional values or game-process access.
"""
from __future__ import annotations
import csv, json, os, shutil, subprocess, sys, tkinter as tk
from datetime import datetime
from pathlib import Path
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageTk

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('DOKKAEBI_DATA_DIR', str(ROOT))).resolve()
DATA.mkdir(parents=True,exist_ok=True)
W,H=1440,810
DARK=(5,10,34,240)
INK='#F1EFFF';SOFT='#C1C7E8';CYAN='#7DDEED';PINK='#D9A6FF';GREEN='#71F4BE'
STATS={
 '공격':[('공격력','수치'),('공격 정확도','수치'),('치명타 적중','수치'),('치명타 피해 증가','%'),('일반 요괴 피해 증가','%'),('보스 피해 증가','%'),('PvP 공격력','수치'),('PvP 공격 정확도','수치'),('인간속성 피해 증가','%')],
 '방어':[('기본 공격 회피','수치'),('방어력','수치'),('도술 막기','수치'),('치명타 저항','수치'),('피해 감소','%'),('일반 요괴 피해 감소','%'),('보스 피해 감소','%'),('PvP 방어력','수치'),('PvP 기본 공격 회피','수치'),('PvP 도술 막기','수치')],
 '기타':[('체력','수치'),('체력 자연 회복','수치'),('이동 속도 증가','%'),('탈것 이동 속도 증가','%'),('체력 물약 소지 제한','수치')],
}
FONT_PATHS=('/usr/share/fonts/truetype/nanum/NanumGothic.ttf','C:/Windows/Fonts/malgun.ttf','DejaVuSans.ttf')
FONT_BOLD=('/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf','C:/Windows/Fonts/malgunbd.ttf')
@lru_cache(maxsize=64)
def font(size=16,bold=False):
    for path in (FONT_BOLD+FONT_PATHS if bold else FONT_PATHS):
        try:return ImageFont.truetype(path,size)
        except OSError:pass
    return ImageFont.load_default()

def text(img,xy,msg,size=15,color=INK,bold=False,anchor=None):
    ImageDraw.Draw(img).text(xy,str(msg),font=font(size,bold),fill=color,anchor=anchor)

def panel(img,xy,fill=(11,20,55,228),stroke=(113,100,190,192),rad=17,width=1):
    ImageDraw.Draw(img).rounded_rectangle(xy,radius=rad,fill=fill,outline=stroke,width=width)

def progress(img,xy,pct,theme=(127,111,249)):
    x1,y1,x2,y2=xy
    panel(img,xy,(20,29,67,241),None,7)
    width=max(2,round((x2-x1-4)*min(1,max(0,pct))))
    panel(img,(x1+2,y1+2,x1+2+width,y2-2),(*theme,255),None,6)

def cover(pic,w,h):
    sw,sh=pic.size; f=max(w/sw,h/sh)
    dst=pic.resize((round(sw*f),round(sh*f)),Image.Resampling.LANCZOS)
    x=(dst.width-w)//2;y=(dst.height-h)//2
    return dst.crop((x,y,x+w,y+h))

def portrait(img,pic,xy):
    x1,y1,x2,y2=xy
    w,h=x2-x1,y2-y1
    src=cover(pic,w,h).convert('RGBA')
    grd=Image.new('RGBA',(w,h),(0,0,0,0));d=ImageDraw.Draw(grd)
    for j in range(h):
        a=round(205*max(0,(j/h-.57)/.43))
        d.line((0,j,w,j),fill=(6,10,36,a))
    src.alpha_composite(grd)
    mask=Image.new('L',(w,h),0)
    ImageDraw.Draw(mask).rounded_rectangle((0,0,w-1,h-1),radius=18,fill=255)
    src.putalpha(mask)
    img.alpha_composite(src,(x1,y1))
    ImageDraw.Draw(img).rounded_rectangle(xy,radius=18,outline=(131,103,231,205),width=2)

def fmt(n,unit='수치'):
    if n is None:return '—'
    try:
        n=float(n)
        if unit=='%':return f'{n:g}%'
        return f'{int(n):,}' if n.is_integer() else f'{n:,.2f}'
    except (ValueError,TypeError):return '—'

def read_rows(path,max_rows=200):
    if not path.is_file():return []
    try:
        with path.open('r',encoding='utf-8-sig',newline='') as f:
            return list(csv.DictReader(f))[-max_rows:]
    except (OSError,UnicodeError,csv.Error):return []

class Dashboard:
    def __init__(self,root):
        self.root=root
        self.root.title('도깨비의 세계 · 성장 기록기 v0.0.1 · 능력치 대시보드')
        self.root.geometry('1580x885');self.root.minsize(1100,650)
        self.root.configure(bg='#080B2A')
        self.page='대시보드';self.stat_page='공격';self.hover=None;self.hits={}
        self.rows=[];self.stats={};self.changes={};self.last_power=None;self.previous_power=None
        self._last_signature=None;self.oldproc=None;self.notice='기록 파일을 읽는 중…'
        self.art=Image.open(ROOT/'assets'/'dashboard_art.png').convert('RGBA')
        self.profile=Image.open(ROOT/'assets'/'dashboard_character.png').convert('RGBA')
        self.bg=cover(self.art,W,H).convert('RGBA')
        dark=Image.new('RGBA',(W,H),(6,9,32,180));self.bg.alpha_composite(dark)
        self.canvas=tk.Canvas(root,bg='#080B2A',highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.photo=None
        self.canvas.bind('<ButtonRelease-1>',self.click)
        self.canvas.bind('<Motion>',self.motion)
        self.canvas.bind('<Configure>',lambda _:self.render())
        self.root.bind('<F5>',lambda _:self.reload())
        self.reload()
        self.root.after(2000,self.auto_refresh)
    def data_signature(self):
        out=[]
        for n in ('combat_power.csv','stat_latest.json','stat_changes.csv'):
            p=DATA/n
            out.append((n,p.stat().st_mtime_ns,p.stat().st_size) if p.exists() else (n,0,0))
        return tuple(out)
    def reload(self):
        self._last_signature=self.data_signature()
        self.rows=read_rows(DATA/'combat_power.csv')
        try:
            loaded=json.loads((DATA/'stat_latest.json').read_text(encoding='utf-8'))
            self.stats=loaded if isinstance(loaded,dict) else {}
        except (OSError,ValueError):self.stats={}
        changes=read_rows(DATA/'stat_changes.csv',200)
        self.changes={}
        for r in changes:
            k=r.get('section','')+'|'+r.get('name','')
            try:self.changes[k]=float(r.get('change',''))
            except (ValueError,TypeError):pass
        valid=[]
        for row in self.rows:
            try:valid.append((int(row['combat_power']),row))
            except (ValueError,KeyError):continue
        self.last_power=valid[-1][0] if valid else None
        self.previous_power=next((n for n,r in reversed(valid[:-1]) if r.get('source','').endswith('_approx')==valid[-1][1].get('source','').endswith('_approx')),None) if valid else None
        self.notice=f'정확 전투력 {fmt(self.last_power)} · 상세 능력치 {len(self.stats)}/24개' if self.last_power is not None else '아직 측정 기록이 없어 · 측정 도구에서 첫 기록을 만들어 봐'
        self.render()
    def auto_refresh(self):
        if not self.root.winfo_exists():return
        if self.data_signature()!=self._last_signature:self.reload()
        self.root.after(2000,self.auto_refresh)
    def place(self,key,rect):self.hits[key]=rect
    def button(self,im,label,rect,key,accent='violet'):
        colors={'violet':((77,61,155,243),(164,137,255,251)),
                'cyan':((25,75,103,240),(112,209,246,245)),
                'pink':((117,39,88,239),(239,133,201,235))}
        bg,stroke=colors[accent]
        if self.hover==key:stroke=(227,217,255,255)
        panel(im,rect,bg,stroke,13,2)
        x1,y1,x2,y2=rect
        text(im,((x1+x2)/2,(y1+y2)/2),label,16,'#FFFFFF',True,'mm')
        self.place(key,rect)
    def header(self,im):
        panel(im,(0,0,W,98),(7,11,38,240),(100,79,184,148),0)
        text(im,(31,23),'도깨비의 세계',31,'#EDE8FF',True)
        text(im,(35,68),'성장 기록기  /  GROWTH TRACKER',12,'#BBB6FF')
        nav=['대시보드','능력치','전투력 기록','측정 도구','설정']
        for i,label in enumerate(nav):
            x=462+i*150;rect=(x,17,x+143,82)
            selected=self.page==label
            if selected:panel(im,rect,(60,49,145,235),(161,124,249,236),12,2)
            elif self.hover=='page:'+label:panel(im,rect,(27,35,88,211),(89,116,189,208),12)
            text(im,(x+71,44),label,17,'#FFFFFF' if selected else '#B9C4EF',selected,'mm')
            self.place('page:'+label,rect)
        text(im,(1410,37),'● 로컬 기록 · 자동 새로고침',13,GREEN,True,'ra')
    def frame(self,im):
        self.header(im)
        text(im,(34,119),self.page,26,'#F5EDFF',True)
        text(im,(1410,124),self.notice[:55],13,'#B8C8F0',False,'ra')
    def draw_stat_rows(self,im,section,rect,limit=None):
        x1,y1,x2,y2=rect
        colors={'공격':('#D5A1FF',(133,88,225,237)),'방어':('#8ACDFF',(58,111,185,234)),'기타':('#82EED6',(45,151,130,236))}
        accent,color=colors[section]
        panel(im,rect,(10,18,50,238),color,17,1)
        text(im,(x1+19,y1+14),section+' 능력치',19,accent,True)
        count=sum(1 for n,_ in STATS[section] if section+'|'+n in self.stats)
        text(im,(x2-20,y1+20),f'{count}/{len(STATS[section])}개',13,'#BAC3E8',False,'ra')
        ImageDraw.Draw(im).line((x1+18,y1+52,x2-18,y1+52),fill=(97,86,153,160),width=1)
        rows=STATS[section] if limit is None else STATS[section][:limit]
        gap=min(29,(y2-y1-71)/max(1,len(rows)))
        for i,(name,unit) in enumerate(rows):
            y=y1+61+i*gap
            key=section+'|'+name
            value=self.stats.get(key)
            text(im,(x1+20,y),name,14,'#C6D1EB')
            # Show the actual delta produced by the last user-verified OCR save.
            delta=self.changes.get(key)
            if delta is None:
                text(im,(x2-19,y),fmt(value,unit),15,'#FFFFFF',True,'ra')
            else:
                text(im,(x2-75,y),fmt(value,unit),14,'#FFFFFF',True,'ra')
                sign='+' if delta>0 else ''
                suffix='%' if unit=='%' else ''
                diff=f'{sign}{delta:g}{suffix}'
                text(im,(x2-17,y+1),diff,11,GREEN if delta>0 else '#FFB6C2' if delta<0 else '#C4CAE2',False,'ra')
            if i%2==1:ImageDraw.Draw(im).line((x1+20,y+23,x2-20,y+23),fill=(67,67,110,90),width=1)
        return count
    def dashboard(self,im):
        # Character portrait, never fabricate a profile from real screenshot content.
        panel(im,(25,151,327,759),(9,17,49,234),(128,101,210,181),18)
        portrait(im,self.profile,(38,165,314,459))
        text(im,(50,478),'내 캐릭터',24,'#EDE5FF',True)
        text(im,(51,516),'전투력 측정 및 성장 기록',14,'#B4BFEA')
        panel(im,(48,550,303,606),(19,30,78,228),(116,107,211,151),11)
        text(im,(62,557),'최근 기록 전투력',12,'#B7C2E9')
        text(im,(64,580),fmt(self.last_power),22,'#FFFFFF',True)
        self.button(im,'전투력 측정 도구 열기',(48,623,305,674),'tool',accent='violet')
        self.button(im,'데이터 폴더 열기',(48,686,305,734),'data',accent='cyan')
        panel(im,(344,151,755,346),(10,20,55,236),(157,111,236,190),18)
        text(im,(366,170),'현재 전투력',21,'#EAD4FF',True)
        text(im,(366,210),fmt(self.last_power),44,'#FFFFFF',True)
        if self.last_power is None: t='정확한 수치를 기록하면 여기에 표시돼'
        elif self.previous_power is None:t='첫 기록 · 비교할 이전 값이 없어'
        else:
            delta=self.last_power-self.previous_power
            t=f'이전 측정 대비  {delta:+,}'
        text(im,(367,281),t,17,GREEN if (self.previous_power is not None and self.last_power>=self.previous_power) else '#DFBDEB')
        text(im,(369,319),'※ HUD의 K 단위가 아닌 캐릭터 정보창 측정을 권장해',12,'#B4BEDC')
        panel(im,(771,151,1414,346),(10,20,55,235),(92,131,212,179),18)
        text(im,(791,170),'전투력 변화 그래프',20,'#D9D0FF',True)
        self.chart(im,(797,211,1388,321))
        self.draw_stat_rows(im,'공격',(344,362,681,760))
        self.draw_stat_rows(im,'방어',(693,362,1062,760))
        self.draw_stat_rows(im,'기타',(1074,362,1414,760))
    def chart(self,im,rect):
        x1,y1,x2,y2=rect;draw=ImageDraw.Draw(im)
        points=[]
        for row in self.rows:
            try:points.append(int(row['combat_power']))
            except (ValueError,KeyError):pass
        points=points[-28:]
        for j in range(4):
            y=y1+(y2-y1)*j/3
            draw.line((x1,y,x2,y),fill=(82,95,152,97),width=1)
        if not points:
            text(im,((x1+x2)/2,(y1+y2)/2),'저장된 전투력 기록이 없어',17,'#B6C0E7',False,'mm');return
        lo=min(points);hi=max(points);span=max(1,hi-lo)
        coords=[]
        for i,v in enumerate(points):
            xx=x1+((x2-x1)*i/max(1,len(points)-1))
            yy=y2-(y2-y1)*(.10+.8*(v-lo)/span)
            coords.append((xx,yy))
        if len(coords)>1:draw.line(coords,fill=(143,171,255,248),width=4,joint='curve')
        for xx,yy in coords[-8:]:draw.ellipse((xx-3,yy-3,xx+3,yy+3),fill=(190,169,255,255))
        text(im,(x2-2,y1+5),fmt(hi),13,'#EAE0FF',False,'ra')
        text(im,(x2-2,y2-15),fmt(lo),13,'#B9B9DF',False,'ra')
    def stat_screen(self,im):
        self.draw_stat_rows(im,'공격',(30,169,471,745))
        self.draw_stat_rows(im,'방어',(486,169,964,745))
        self.draw_stat_rows(im,'기타',(979,169,1411,745))
        text(im,(42,757),'표시는 저장된 값만 사용해. 증가·감소량은 전투력 기록 화면에서 확인할 수 있어.',14,'#B6C9E3')
    def history(self,im):
        panel(im,(29,167,930,759),(11,19,52,237),(116,100,195,181),17)
        text(im,(49,183),'전투력 측정 기록',21,'#FFFFFF',True)
        cols=[('기록 시각',54),('전투력',395),('직전 변화',599),('측정 방식',751)]
        for name,x in cols:text(im,(x,235),name,15,'#D6CBFF',True)
        rows=list(reversed(self.rows[-14:]))
        if not rows:text(im,(55,310),'아직 측정 기록이 없어.',19,'#D1C6E9')
        for i,r in enumerate(rows):
            y=274+i*31
            if i%2==0:panel(im,(47,y-4,912,y+26),(26,33,82,130),None,6)
            ts=r.get('timestamp','')[:19].replace('T',' ')
            text(im,(54,y),ts,13,INK)
            text(im,(395,y),fmt(r.get('combat_power')),15,'#FFFFFF',True)
            try:change=float(r['change']);change=f'{change:+,.0f}'
            except (ValueError,KeyError):change='—'
            text(im,(599,y),change,14,GREEN if change.startswith('+') else '#FFB1B7' if change.startswith('-') else '#BFC8E0')
            source='근삿값 (HUD)' if r.get('source','').endswith('_approx') else '정확값 (상세창)'
            text(im,(752,y),source,12,'#C3C6E7')
        panel(im,(946,167,1413,759),(11,19,52,238),(96,110,191,181),17)
        text(im,(970,186),'성장 흐름',21,'#FFFFFF',True)
        self.chart(im,(973,251,1385,452))
        text(im,(971,489),f'총 {len(self.rows)}회 측정 기록',19,'#CFC1FF',True)
        text(im,(971,534),'상세 능력치 변경 기록은',14,'#B9C5E3')
        text(im,(971,561),'stat_changes.csv에서 볼 수 있어.',14,'#B9C5E3')
        self.button(im,'전투력 CSV 열기',(977,638,1377,687),'powercsv',accent='cyan')
    def measurement(self,im):
        panel(im,(63,167,1378,749),(11,20,54,236),(142,105,218,181),22)
        text(im,(93,202),'게임을 종료하지 않고 측정할 수 있어',27,'#FFFFFF',True)
        info=[('01','캐릭터 정보창 열기','게임에서 정보창을 열고 왼쪽 위 정확한 전투력 숫자를 보여줘.'),
              ('02','DXcam 캡처 진단','전체화면이 검정색으로 잡히면 DXcam과 모니터 번호를 확인해.'),
              ('03','공격·방어·기타 탭 측정','각 탭의 숫자를 사용자가 확인한 뒤 저장할 수 있어.'),
              ('04','2초 이내 기록 반영','기록기를 닫지 않아도 이 화면의 값이 자동 갱신돼.')]
        for i,(num,t,d) in enumerate(info):
            y=281+i*87
            panel(im,(93,y,1351,y+76),(24,35,86,207),(86,101,170,141),12)
            text(im,(116,y+21),num,25,CYAN,True)
            text(im,(169,y+10),t,19,'#FFFFFF',True)
            text(im,(169,y+42),d,15,'#BCCBE9')
        self.button(im,'새 측정 센터 열기',(106,665,538,724),'tool','violet')
        self.button(im,'기록 폴더 열기',(566,665,955,724),'data','cyan')
        self.button(im,'새로고침  F5',(990,665,1339,724),'refresh','violet')
    def settings(self,im):
        panel(im,(68,165,1380,742),(11,19,52,237),(119,100,191,193),19)
        text(im,(95,201),'기록과 프로그램 파일은 분리해서 관리해',25,'#FFFFFF',True)
        info=[('전투력 CSV',str(DATA/'combat_power.csv')),
              ('능력치 최신값',str(DATA/'stat_latest.json')),
              ('능력치 변경 내역',str(DATA/'stat_changes.csv')),
              ('데이터 폴더',str(DATA)),
              ('자동 갱신','2초마다 새 기록 확인 / F5 수동 새로고침'),
              ('측정 기능','새로운 판타지 측정 센터에서 실행')]
        for i,(a,b) in enumerate(info):
            y=275+i*56
            panel(im,(91,y,1358,y+48),(25,33,82,164),(74,82,156,125),9)
            text(im,(113,y+12),a,15,'#D3C7FF',True)
            text(im,(385,y+12),b[:94],14,'#E7EDFF')
        self.button(im,'백업 ZIP 만들기',(100,661,497,713),'backup')
        self.button(im,'설정 및 기록 폴더 열기',(523,661,966,713),'data','cyan')
        self.button(im,'측정 센터 설정 열기',(987,661,1354,713),'tool')
    def render(self):
        if not self.root.winfo_exists():return
        im=self.bg.copy();self.hits={}
        self.frame(im)
        if self.page=='대시보드':self.dashboard(im)
        elif self.page=='능력치':self.stat_screen(im)
        elif self.page=='전투력 기록':self.history(im)
        elif self.page=='측정 도구':self.measurement(im)
        else:self.settings(im)
        cw=max(1,self.canvas.winfo_width());ch=max(1,self.canvas.winfo_height())
        if (cw,ch)!=(W,H): im=im.resize((cw,ch),Image.Resampling.BILINEAR)
        self.photo=ImageTk.PhotoImage(im.convert('RGB'))
        self.canvas.delete('all');self.canvas.create_image(0,0,anchor='nw',image=self.photo)
    def hit(self,x,y):
        return next((k for k,r in reversed(list(self.hits.items())) if r[0]<=x<=r[2] and r[1]<=y<=r[3]),None)
    def loc(self,event):return event.x/max(1,self.canvas.winfo_width())*W,event.y/max(1,self.canvas.winfo_height())*H
    def motion(self,event):
        new=self.hit(*self.loc(event))
        if self.hover!=new:
            self.hover=new;self.canvas.configure(cursor='hand2' if new else 'arrow')
            # Don't repaint 90MB of screenshots on every pixel, only on meaningful button hover.
            if new in ('tool','data','backup','powercsv','refresh') or self.hover in ('tool','data','backup','powercsv','refresh'):self.render()
    def click(self,event):
        key=self.hit(*self.loc(event))
        if not key:return
        if key.startswith('page:'):
            self.page=key[5:];self.render();return
        if key=='refresh':self.reload();return
        if key=='tool':
            entry=ROOT/'legacy_tracker'/'tracker.py'
            if not entry.is_file():
                from tkinter import messagebox
                messagebox.showerror('측정 도구','OCR 측정기 파일이 없어. 설치 상태를 확인해 줘.',parent=self.root);return
            if self.oldproc is not None and self.oldproc.poll() is None:
                from tkinter import messagebox
                messagebox.showinfo('측정기 실행 중','측정기가 이미 열려 있어. 작업 표시줄에서 확인해 줘.',parent=self.root);return
            env=os.environ.copy();env['DOKKAEBI_DATA_DIR']=str(DATA);env['DOKKAEBI_ASSETS_DIR']=str(DATA/'assets')
            log=(DATA/'ocr_errors.log').open('a',encoding='utf-8')
            try:self.oldproc=subprocess.Popen([sys.executable,str(entry)],cwd=entry.parent,env=env,
                 stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            finally:log.close()
            return
        if key in ('data','powercsv'):
            path=DATA if key=='data' else DATA/'combat_power.csv'
            if not path.exists():path=DATA
            try:
                if os.name=='nt':os.startfile(str(path))
                elif sys.platform=='darwin':subprocess.Popen(['open',str(path)])
                else:subprocess.Popen(['xdg-open',str(path)])
            except OSError:pass
            return
        if key=='backup':
            import zipfile
            from tkinter import messagebox
            backups=DATA.parent/'backups';backups.mkdir(exist_ok=True,parents=True)
            date=datetime.now().strftime('%Y%m%d_%H%M%S')
            out=backups/f'growth_records_{date}.zip'
            with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
                for name in ('combat_power.csv','stat_latest.json','stat_snapshots.csv','stat_changes.csv','config.json'):
                    f=DATA/name
                    if f.is_file():z.write(f,name)
            messagebox.showinfo('백업 완료',f'기존 기록을 변경하지 않고 ZIP 백업을 만들었어.\n{out}',parent=self.root)

def main():
    root=tk.Tk();Dashboard(root);root.mainloop()
if __name__=='__main__':main()
