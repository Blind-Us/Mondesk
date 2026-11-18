<p align="center"><img src="assets/mondesk.png" width="128" alt="Mondesk"></p>

# Mondesk

[中文](README.md) ｜ **English**

Back at your desk every Monday, and the little screen beside you keeps an eye on everything else.

<p align="center"><img src="docs/images/panel.png" width="720" alt="The Mondesk panel"></p>

## Cards

- **3D printer** (Bambu Lab): progress, time left, model preview, chamber camera
- **Now Playing**: Apple Music synced lyrics; YouTube and Bilibili videos played in sync on the small screen
- **AI usage**: Codex / Claude 5-hour and 7-day quota
- **Companion**: an AI character with a face that watches all of the above and speaks up
- **Weather**, **Clock** (with timer and stopwatch), **System** (volume, monitor brightness)

Drag cards to move and resize them, and switch the whole layout between modes such as Focus / Print / Rest.

## Download

Get it from [Releases](../../releases). Unzip and double-click; no Python to install.

| System | File | Open |
|---|---|---|
| Windows 10/11 | `Mondesk-windows.zip` | `Mondesk.exe` |
| Linux | `Mondesk-linux.tar.gz` | `./Mondesk` (the panel opens in your browser) |

- Start with the computer, full screen: the "應用程式" (Application) section of the settings page.
- Apple Music lyrics and video sync need the browser extension; the "正在播放" (Now Playing) section of the settings page explains how to install it.
- If Windows says "Windows protected your PC", click "More info" → "Run anyway" (the program is not code-signed). On computers with Smart App Control turned on, use the source version.

The interface is in Traditional Chinese.

## Install from source

Needs Python 3.10 or later.

```bash
Mondesk.bat         # Windows
./mondesk.sh        # Linux
```

The first start sets up the environment and packages by itself. Settings live in `%LOCALAPPDATA%\DeskMon` (Linux: `~/.config/DeskMon`), not in the program folder. The panel can also be opened in a browser: <http://127.0.0.1:9361>.

## Settings and accounts

**Every credential is entered by you on the settings page, and the only source of settings is the local user config.** The browser connector's pairing data is generated from it into the same user folder and is never part of a release package.
When the settings page reads the settings, secret fields such as access codes show only `••••••`: the real values stay in the settings file on your computer and are used only by the local Mondesk program (`127.0.0.1`); not even the settings page receives them, and they are never uploaded anywhere.

| Feature | Needs | Default |
|---|---|---|
| Bambu printer | Printer IP, serial number, LAN access code (shown on the printer's screen) | Off |
| Official Claude % | Having signed in with the `claude` command (Claude Code) on this computer | Off, turn it on yourself |
| Companion (Claude) | An Anthropic API key (on the settings page, or the `ANTHROPIC_API_KEY` environment variable); or a local Ollama model, or free rule-based lines | Off |
| Apple Music synced lyrics | Pair with `python -m modules.apple_bridge` and load `apple-music-extension` in Chrome (lyrics come from Apple Music only) | Off |

## External services it contacts

Mondesk binds to `127.0.0.1` only. These are the places it connects to; anything not on by default must be turned on in settings:

| Service | Purpose | Data sent | Default |
|---|---|---|---|
| Your printer (LAN) | Status, preview, camera | None (receive only) | On once configured |
| iTunes Search API | Cover art, song length | Song title, artist | On |
| Anthropic | Official Claude usage % | Your Claude Code sign-in token | Off |
| Anthropic Messages API | Companion lines (with the Claude brain) | Event name, time, continuous work time, and print status, song title and AI usage queried by the model | Off |
| Ollama (local) | Companion local model (with the Ollama brain) | Same as above, sent only to your own computer | Off |
| Open-Meteo; the Norwegian Meteorological Institute (api.met.no) when unreachable | Forecast, place search on the settings page | Latitude/longitude of the place you chose; the place name you type when searching | Off (on once a weather card is placed and a place chosen) |

Note: official Claude usage, the Apple Music extension and the Bambu Studio camera tool are **not official public interfaces**. They may break when the other side changes, and you should check each service's terms yourself before using them.

## Security

- The server only accepts requests from this computer (`127.0.0.1` / `localhost`) and from Mondesk's own pages;
  every write API requires an `X-DeskMon` header, so other websites cannot change settings or trigger actions for you.
- "Open Bambu Studio" only starts a program named `bambu-studio`.
- The printer is **watch-only** by default. Recent Bambu firmware in cloud mode rejects control commands from unofficial software (error 84033543); use Bambu Studio / Handy for control.

## Chamber camera

Bambu Studio's camera tool (`bambu_source`) is preferred: it works in cloud mode and needs no LAN Only Liveview.
When it is not running, the printer's LAN stream is used instead (LAN Only Liveview must be enabled on the printer).

## Development

```bash
python tools/check.py                        # packages, all tests, demo server
python -m unittest discover -s tests -t .    # Python tests only
node --test tests/*.cjs                      # JavaScript tests only (Node.js 18+)
python tools/companion_eval.py               # Companion fixed event set and a day's line count
```

- New data source: follow the contract in [docs/MODULES.md](docs/MODULES.md); `modules/weather.py` is the example.
- The three video display paths and when they are released: [docs/VIDEO.md](docs/VIDEO.md).
- What each card shows at each size and its minimum size: [docs/LAYOUT.md](docs/LAYOUT.md).
- Themes (background, shape, accent colour, per-card colours, modes and night, following the cover): [docs/THEME.md](docs/THEME.md).
- On-device acceptance steps: [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md); status and to-do: [docs/ROADMAP.md](docs/ROADMAP.md).

The documents under `docs/` are in Chinese.

## License

[MIT](LICENSE)
