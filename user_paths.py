"""Runtime settings belong to the user; packaged resources are read-only."""
import os
from pathlib import Path


def user_config_path():
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share'))) if os.name == 'nt' else Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    return base / 'DeskMon' / 'config.json'


def user_data_dir():
    """Folder for everything DeskMon writes while running (settings, caches, logs, imported
    characters, the generated browser extension). The program folder is never written to, so
    it can be read-only or replaced by an update without losing anything."""
    path = user_config_path().parent
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_user_config(template):
    path = user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        # Older versions kept settings next to the program (config.json beside the template).
        # Carry them over so moving to the per-user location never loses the printer access
        # code, the Apple Music pairing key or the theme.
        legacy = Path(template).with_name('config.json')
        path.write_bytes((legacy if legacy.is_file() else Path(template)).read_bytes())
    return path
