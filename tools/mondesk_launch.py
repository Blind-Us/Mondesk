"""Part of the Windows package (tools/build_app.py copies it next to the packages, with a .pth line
that imports it whenever that Python starts).

Mondesk.exe is Python's own pythonw.exe, renamed: it keeps the Python Software Foundation's signature,
so Windows' Smart App Control lets it run, where it refuses unsigned programs and any .bat downloaded
from the web. Started with nothing after it (a double click, or "start with the computer"), it runs
Mondesk instead of an empty Python. Any other start of this Python is left alone.

    Mondesk.exe              the panel
    Mondesk 示範模式.exe      the demo (the same program under another name)
    MONDESK_SELF_TEST=<file> the build's check that the package really starts
"""
import os
import subprocess
import sys
import traceback
from pathlib import Path

# This runs while Python is still starting up (from a .pth file), which is too early for the window
# (pywebview's .NET part crashes). So it only starts the same signed program once more, the ordinary way,
# with Mondesk's own script, and leaves; that second start runs Mondesk once Python is fully up.
_name = Path(sys.executable).stem.lower()
if _name.startswith("mondesk") and len(getattr(sys, "orig_argv", ())) == 1:
    _script = Path(sys.executable).parent / "app" / "desktop.py"
    _args = [] if _name == "mondesk" else ["--demo"]
    _test = os.environ.get("MONDESK_SELF_TEST")
    if _test:
        _args = ["--self-test", _test]
    _code = 0
    try:
        _child = subprocess.Popen([sys.executable, str(_script), *_args], cwd=str(_script.parent))
        if _test:
            _code = _child.wait()
    except BaseException:
        _code = 1
        try:   # a window-less program has nowhere to print: leave the reason next to the settings
            from user_paths import user_data_dir
            (user_data_dir() / "start-error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
    os._exit(_code)   # never fall through into an interactive Python
