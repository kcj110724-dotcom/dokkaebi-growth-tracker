"""Pure parser and OCR helpers for the user's on-screen stats. No game process access."""
import re
from collections import Counter
from PIL import ImageOps
import pytesseract

STATS = {
    '공격': [
        ('공격력', '수치'), ('공격 정확도','수치'), ('치명타 적중','수치'),
        ('치명타 피해 증가','%'), ('일반 요괴 피해 증가','%'), ('보스 피해 증가','%'),
        ('PvP 공격력','수치'), ('PvP 공격 정확도','수치'), ('인간속성 피해 증가','%'),
    ],
    '방어': [
        ('기본 공격 회피','수치'), ('방어력','수치'), ('도술 막기','수치'),
        ('치명타 저항','수치'), ('피해 감소','%'), ('일반 요괴 피해 감소','%'),
        ('보스 피해 감소','%'), ('PvP 방어력','수치'),
        ('PvP 기본 공격 회피','수치'), ('PvP 도술 막기','수치'),
    ],
    '기타': [
        ('체력','수치'), ('체력 자연 회복','수치'), ('이동 속도 증가','%'),
        ('탈것 이동 속도 증가','%'), ('체력 물약 소지 제한','수치'),
    ]
}
ALL_FIELDS = [(section, name, unit) for section, fields in STATS.items() for name,unit in fields]


def parse_power_text(raw):
    s = re.sub(r'\s+', '', raw.upper()).replace('O', '0').replace('，', ',').replace('．', '.')
    m = re.search(r'(\d{2,4})[.,](\d{1,2})K', s)
    if m:
        whole, fraction = m.groups()
        return (int(whole)*1000 + int(fraction.ljust(2, '0'))*10, True)
    m = re.search(r'(?<!\d)(\d{5,6})K', s)
    if m:
        ds = m.group(1)
        return (int(ds[:-2])*1000 + int(ds[-2:])*10, True)
    if 'K' in s: return None
    m = re.search(r'(?<!\d)(\d{1,3}(?:,\d{3})+)(?!\d)', s)
    if m: return (int(m.group(1).replace(',','')), False)
    ds = re.findall(r'(?<!\d)(\d{5,8})(?!\d)', s)
    return (int(ds[0]), False) if len(ds) == 1 else None


def parse_stat(raw, unit):
    s = raw.strip().replace(' ', '').replace('O','0').replace('o','0')
    s = s.replace('，', ',').replace('．', '.').replace('％', '%')
    s = re.sub(r'[^0-9.,%]', '', s)
    if not s: return None
    if unit == '%':
        s = s.replace('%', '').replace(',', '.')
        if not re.fullmatch(r'\d+(?:\.\d{1,3})?', s): return None
        v = float(s)
        # Percent changes above 100% are unusual here, and often lost-decimal OCR.
        if not 0 <= v <= 100: return None
        return round(v, 3)
    s = s.replace('%', '')
    if re.fullmatch(r'\d{1,3}(?:,\d{3})+', s):
        return int(s.replace(',',''))
    if re.fullmatch(r'\d{1,3}(?:\.\d{3})+', s):
        return int(s.replace('.',''))
    if re.fullmatch(r'\d{1,9}', s): return int(s)
    return None


def _ocr_text(img, psm=7, power=False):
    opts = '0123456789,.Kk' if power else '0123456789,.%'
    return pytesseract.image_to_string(img, config=f'--psm {psm} -c tessedit_char_whitelist={opts}').strip()


def _preprocess(img):
    gray = ImageOps.autocontrast(ImageOps.grayscale(img))
    gray = gray.resize((max(1,gray.width*5), max(1,gray.height*5)))
    return (gray, ImageOps.invert(gray))


def read_power(img):
    found=[]
    for prep in _preprocess(img):
        for psm in (7, 13):
            raw = _ocr_text(prep, psm, True)
            parsed = parse_power_text(raw)
            if parsed and 1000 <= parsed[0] <= 100000000:
                found.append(parsed)
    if not found: return None
    c = Counter(found)
    top, votes = c.most_common(1)[0]
    # Two agreeing decodes required if there was a conflicting reading.
    return top if len(c) == 1 or votes >= 2 else None


def read_stat_rows(column_img, section):
    """The selected column must span ten equally spaced rows (defense tab)."""
    rows = []
    length = len(STATS[section])
    for i,(name,unit) in enumerate(STATS[section]):
        y0 = round(column_img.height*i/10)
        y1 = round(column_img.height*(i+1)/10)
        row = column_img.crop((0,y0,column_img.width,y1))
        found=[]
        for prep in _preprocess(row):
            raw=_ocr_text(prep,7)
            found.append((raw,parse_stat(raw,unit)))
        valid=[v for _,v in found if v is not None]
        if not valid:
            value=None;uncertain=True
        else:
            counter=Counter(valid)
            value=counter.most_common(1)[0][0]
            uncertain=len(counter)>1
        rows.append({'name':name,'unit':unit,'value':value,'uncertain':uncertain,
                     'ocr_text':' / '.join(x[0] for x in found)})
    return rows


def read_power_exact(img):
    """Read ONLY full, orange combat power in the character details panel.

    Intentionally rejects HUD 'K' estimates and UI when the details panel is closed.
    Returns (number, False), or None. No game memory or input access.
    """
    from PIL import Image, ImageOps
    import statistics

    rgb=img.convert('RGB')
    if rgb.width < 40 or rgb.height < 12:
        return None
    # Character panel's power is gold on a dark background, not the outdoor HUD.
    pixels=list(rgb.getdata())
    dark=sum(1 for r,g,b in pixels if (r*0.299 + g*0.587 + b*0.114) < 100)
    if dark/len(pixels) < .50:
        return None
    # An explicit golden-text mask rejects the white ranking and sword icons.
    mask=Image.new('L',rgb.size)
    mask.putdata([255 if (r>115 and r>g*1.10 and g>b*1.12 and r-b>52) else 0 for r,g,b in pixels])
    if sum(1 for v in mask.getdata() if v>0)/len(pixels) < .018:
        return None
    found=[]
    for source in (mask, ImageOps.autocontrast(ImageOps.grayscale(rgb))):
        expanded=source.resize((source.width*5,source.height*5))
        for psm in (7,6):
            raw=_ocr_text(expanded,psm,False)
            cleaned=re.sub(r'\s+','',raw).replace('O','0').replace('.',',')
            match=re.search(r'(?<!\d)(\d{1,3},\d{3}|\d{5,8})(?!\d)',cleaned)
            if not match:continue
            number=int(match.group(1).replace(',',''))
            if 10000<=number<=99999999:
                found.append(number)
    if not found:return None
    best,count=Counter(found).most_common(1)[0]
    # Only accept if OCR independent renderings agree, avoiding phantom digits.
    return (best,False) if count>=2 else None


def read_power_hud(img):
    """Optional approximate HUD mode: NEVER trust a bare numeric OCR result.

    Only an explicit K reading can enter the HUD log; saves like 72,251
    without a K suffix (seen in v3) are rejected.
    """
    found=[]
    for prep in _preprocess(img):
        for psm in (7,13):
            raw=_ocr_text(prep,psm,True)
            parsed=parse_power_text(raw)
            if parsed is not None and parsed[1] is True:
                found.append(parsed)
    if not found:return None
    result,votes=Counter(found).most_common(1)[0]
    return result if votes>=2 else None
