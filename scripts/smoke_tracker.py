"""Windows CI smoke test; real game capture/launcher tests remain manual."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile
from prepare_release import validate_zip


def smoke(asset):
    payload = Path(asset).read_bytes()
    with zipfile.ZipFile(asset) as archive:
        version = json.loads(archive.read('manifest.json'))['version']
    validate_zip(payload, version, 'tracker')
    with tempfile.TemporaryDirectory(prefix='dokkaebi-smoke-') as folder:
        root = Path(folder)
        with zipfile.ZipFile(asset) as archive:
            archive.extractall(root / 'package')
        data = root / 'user_data'
        data.mkdir()
        (data / 'combat_power.csv').write_text(
            'timestamp,combat_power,change,source\n2026-01-01T12:00:00,123456,,screen_ocr_exact\n',
            encoding='utf-8-sig')
        (data / 'stat_latest.json').write_text(json.dumps({'공격|공격력': 100}), encoding='utf-8')
        (data / 'config.json').write_text('{"font_size": 14}', encoding='utf-8')
        before = {p.name: p.read_bytes() for p in data.iterdir()}
        os.environ['DOKKAEBI_DATA_DIR'] = str(data)
        os.environ['DOKKAEBI_ASSETS_DIR'] = str(data / 'assets')
        app = root / 'package/app'
        spec = importlib.util.spec_from_file_location('dashboard_smoke', app / 'tracker.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        window = module.tk.Tk()
        window.withdraw()
        try:
            dashboard = module.Dashboard(window)
            for page in ('대시보드', '능력치', '전투력 기록', '측정 도구', '설정'):
                dashboard.page = page
                dashboard.render()
                window.update_idletasks()
            assert dashboard.last_power == 123456
            assert dashboard.stats['공격|공격력'] == 100
        finally:
            window.destroy()
        sys.path.insert(0, str(app / 'legacy_tracker'))
        import ui_v9  # noqa: F401
        assert all((data / name).read_bytes() == content for name, content in before.items())
        assert not list(app.rglob('config.json')), 'Records must stay outside the package'
    print('Packaged dashboard pages rendered; isolated CSV/JSON preserved; measurement modules imported')


if __name__ == '__main__':
    smoke(sys.argv[1])
