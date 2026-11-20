"""Exercise the source launcher without installing packages or opening a browser."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which('sh'), 'POSIX shell required')
class LinuxLauncherTests(unittest.TestCase):
    def run_launcher(self, windows):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copyfile(ROOT / 'mondesk.sh', root / 'mondesk.sh')
            bindir = root / 'bin'
            bindir.mkdir()
            bootstrap = bindir / 'python3'
            bootstrap.write_text("""#!/bin/sh
mkdir -p "$3/bin"
cat > "$3/bin/python" <<'EOF'
#!/bin/sh
printf '%s\\n' "$*" >> calls
EOF
chmod +x "$3/bin/python"
""")
            bootstrap.chmod(0o755)
            if windows:
                (root / '.venv' / 'Scripts').mkdir(parents=True)
                (root / '.venv' / 'Scripts' / 'python.exe').write_bytes(b'windows')
            env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ['PATH'])
            for _ in range(2):
                subprocess.run(['sh', 'mondesk.sh', '--demo', '--browser'], cwd=root,
                               env=env, check=True, capture_output=True, text=True)
            calls = (root / 'calls').read_text().splitlines()
            self.assertEqual(calls, ['-m pip install -q -r ' + ('requirements.txt' if os.uname().sysname == 'Linux' else 'requirements-desktop.txt'),
                                     'desktop.py --demo --browser', 'desktop.py --demo --browser'])
            venv = '.venv-linux' if windows else '.venv'
            self.assertTrue((root / venv / 'bin' / 'python').is_file())
            if windows:
                self.assertEqual((root / '.venv/Scripts/python.exe').read_bytes(), b'windows')

    def test_fresh_checkout_and_second_launch(self):
        self.run_launcher(False)

    def test_windows_environment_is_preserved(self):
        self.run_launcher(True)
