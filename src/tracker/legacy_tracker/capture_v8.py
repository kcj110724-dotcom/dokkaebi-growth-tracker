"""Windows screen capture for Dokkaebi v8.

Uses DXcam (Desktop Duplication) when possible, with MSS/ImageGrab alternatives.
A screenshot-file fallback supports ROI selection, without claiming it enables
live OCR when screen capture is blocked. Nothing touches game memory/process.
"""
from PIL import Image
import time

DXCAM_LABEL='DXcam (게임 전체화면)'

class CaptureError(RuntimeError):
    pass


def likely_black_fullscreen(image):
    """Detect missing DirectX content with a visible Windows taskbar.

    Screenshots of largely black games are possible; this is an advisory test
    only, applied to ROI *selection*, not to automatic OCR measurements.
    """
    if image.width < 200 or image.height < 150:
        return False
    test=image.convert('RGB').crop((0,0,image.width,int(image.height*.91)))
    test.thumbnail((128,80),Image.Resampling.NEAREST)
    samples=list(test.getdata())
    if not samples:return True
    dark=sum(1 for r,g,b in samples if max(r,g,b)<15)
    return dark/len(samples)>.88


def dxcam_capture(region, monitor, output_idx):
    try:
        import dxcam
    except ImportError as err:
        raise CaptureError('DXcam 라이브러리가 아직 없어. 이 폴더에서 py -m pip install -r requirements.txt 를 실행해 줘.') from err
    x=region['left']-monitor['left'];y=region['top']-monitor['top']
    w,h=region['width'],region['height']
    if x<0 or y<0 or x+w>monitor['width'] or y+h>monitor['height']:
        raise CaptureError('선택한 전투력 영역이 현재 모니터 바깥이야. 캡처할 모니터/영역을 다시 선택해 줘.')
    try:
        camera=dxcam.create(output_idx=output_idx,backend='dxgi',output_color='RGB',processor_backend='numpy')
        try:
            frame=camera.grab(region=(x,y,x+w,y+h),new_frame_only=False)
            if frame is None:
                camera.start(target_fps=5)
                try:
                    for _ in range(4):
                        time.sleep(.13)
                        frame=camera.get_latest_frame()
                        if frame is not None:break
                finally:
                    camera.stop()
            if frame is None:
                raise CaptureError('DXcam에서 화면이 아직 들어오지 않았어. 게임 창을 표시한 상태로 다시 시도해 줘.')
            img=Image.fromarray(frame).convert('RGB')
            if img.size != (w,h):
                raise CaptureError(f'DXcam 캡처 크기 불일치({img.size}, 기대 {(w,h)}). 다른 모니터 선택 또는 창 모드를 시도해 줘.')
            return img
        finally:
            camera.release()
    except CaptureError:
        raise
    except Exception as err:
        raise CaptureError(f'DXcam 캡처 실패: {err}. 게임을 테두리 없는 창 모드로 바꾸거나 ImageGrab을 사용해 봐.') from err


def screenshot_for_monitor(image, monitor, monitors):
    """Extract the selected display from a Windows full virtual-desktop screenshot."""
    image=image.convert('RGB')
    size=(monitor['width'],monitor['height'])
    if image.size==size:return image
    if abs(image.width-size[0])<=2 and abs(image.height-size[1])<=2:
        return image.resize(size,Image.Resampling.BILINEAR)
    xmin=min(m['left'] for m in monitors)
    ymin=min(m['top'] for m in monitors)
    xmax=max(m['left']+m['width'] for m in monitors)
    ymax=max(m['top']+m['height'] for m in monitors)
    if image.size==(xmax-xmin,ymax-ymin):
        x=monitor['left']-xmin;y=monitor['top']-ymin
        return image.crop((x,y,x+monitor['width'],y+monitor['height']))
    raise CaptureError(f'스크린샷 크기 {image.width}×{image.height}, 선택 모니터 {size[0]}×{size[1]}가 달라. 전체 화면 스크린샷을 선택해 줘.')
