"""Render the actual popup methods without opening windows or accessing user data."""
import importlib.machinery
import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]

def render():
    path = ROOT / 'src/launcher/launcher.pyw'
    loader = importlib.machinery.SourceFileLoader('launcher_preview', str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    launcher = module.Launcher.__new__(module.Launcher)
    launcher._update_art = module.Image.open(path.parent / 'assets/update_discovery_art.png').convert('RGBA')
    launcher._done_art = module.Image.open(path.parent / 'assets/update_success_art.png').convert('RGBA')
    launcher.release = {'version': '0.0.3'}
    launcher.notes = '검증용 업데이트 안내'
    launcher.update_kind = 'launcher'
    launcher.launcher_manager = SimpleNamespace(active=lambda: '0.0.2')
    launcher.store = SimpleNamespace(state={'current': '0.0.1'})
    output = ROOT / 'dist/previews'
    output.mkdir(parents=True, exist_ok=True)
    images = []
    for name, completed in [('discovery', False), ('success', True)]:
        launcher.modal = 'restart_required' if completed else 'update'
        launcher.hit = {}
        image = module.Image.new('RGBA', (1440, 810), '#080E29')
        assert launcher._illustrated_modal(image, completed)
        box = launcher.hit['modal:close']
        assert box == (1044, 86, 1096, 138), box
        assert 325 < box[0] < box[2] < 1115 and 68 < box[1] < box[3] < 744
        image.save(output / (name + '.png'))
        images.append(image.tobytes())
    assert images[0] != images[1]
    print('Distinct popups rendered; close hitbox inside popup:', box)

if __name__ == '__main__':
    render()
