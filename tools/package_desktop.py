"""Build a cross-platform source desktop package using a strict public-file allowlist."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def build(output=None):
    output = Path(output) if output else ROOT / 'dist' / 'DeskMon-desktop.zip'
    output.parent.mkdir(parents=True, exist_ok=True)
    files = [ROOT / name for name in ('desktop.py', 'server.py', 'user_paths.py', 'displays.py',
             'requirements.txt', 'requirements-desktop.txt', 'config.example.json', 'README.md', 'LICENSE',
             'run.bat', 'run.sh', 'run-desktop.bat', 'run-desktop.sh',
             'run-demo.bat', 'run-demo.sh', 'check.bat', 'check.sh')]
    files += list((ROOT / 'modules').glob('*.py'))
    # the self-check (tools/check.py) runs the tests, so they ship too; docs explain the rest
    files += [ROOT / 'tools' / name for name in ('check.py', 'companion_eval.py', 'companion_bench.py', 'companion_report.py', 'package_desktop.py')]
    files += [p for p in (ROOT / 'tests').iterdir() if p.is_file() and p.suffix in ('.py', '.cjs')]
    files += [p for p in (ROOT / 'apple-music-extension').glob('test-*.cjs')]
    files += list((ROOT / 'docs').glob('*.md'))
    files += [p for p in (ROOT / 'web').rglob('*') if p.is_file() and p.suffix in ('.html', '.js', '.css', '.svg', '.json')]
    files += [p for p in (ROOT / 'apple-music-extension').iterdir()
              if p.is_file() and p.name != 'config.js' and p.suffix in ('.json', '.js', '.html', '.md')]
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(files)):
            archive.write(path, 'DeskMon/' + path.relative_to(ROOT).as_posix())
    return output


if __name__ == '__main__':
    print(build())
