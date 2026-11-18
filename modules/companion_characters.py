"""Companion character packs: a small, shareable format so anyone can make or import a face.

A pack is a folder (or a .zip of it) with a `character.json`:

    {
      "format": "deskmon-character/1",
      "id": "sunny",                      # optional; derived from the name otherwise
      "name": "Sunny",
      "author": "you",                    # optional
      "description": "...",               # optional
      "persona": "開朗、愛吐槽的小太陽",  # optional, <= 300 chars, flavours how it talks
      "faces": {
        "neutral": "neutral.png",         # a file in the pack (png, webp, gif, jpg, svg) ...
        "happy": "😄",                    # ... or a short text/emoji drawn huge
        ...
      }
    }

Face names: neutral (required), happy, thinking, worried, surprised, sleepy, talk_open,
talk_closed. Missing expressions fall back to neutral; without talk_open/talk_closed the
character bounces while it talks instead of moving its mouth.

Animated packs add a "sprite": one sprite sheet (a grid of equal cells) and, per face, the
row to play and how many frames it has:

      "sprite": {"sheet": "spritesheet.webp", "columns": 8, "cell": [192, 208],
                 "faces": {"neutral": [0, 6], "happy": [4, 5], ...}}

Codex pets (pet.json + spritesheet.webp, 8 x 9 cells of 192 x 208) are read as such packs:
from a .zip, from a folder in the characters folder, or straight from the Codex pets folder
(~/.codex/pets), so a pet installed for Codex shows up in Mondesk by itself.

Built-in packs live in web/companion/<id>/, the user's in <user folder>/characters/<id>/.
A user folder without character.json but with neutral.png etc. also works.
"""
import hashlib
import io
import json
import os
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .companion_brain import FACE_NAMES

ROOT = Path(__file__).resolve().parent.parent
BUILTIN_DIR = ROOT / "web" / "companion"
FORMAT = "deskmon-character/1"
DEFAULT_ID = "emoji"
IMAGE_TYPES = {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif", ".jpg": "image/jpeg",
               ".jpeg": "image/jpeg", ".svg": "image/svg+xml"}
MAX_PACKAGE = 10 * 1024 * 1024     # uploaded file
MAX_IMAGE = 4 * 1024 * 1024        # one face image
MAX_SHEET = 8 * 1024 * 1024        # one sprite sheet
MAX_UNPACKED = 24 * 1024 * 1024    # all images of one pack
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHEET = "sheet"                    # /api/companion/character/<id>/sheet serves the sprite sheet
CODEX_PREFIX = "codex-"            # ids of pets read from the Codex pets folder
# Codex pet sheet: 8 columns of 192 x 208 cells, one animation per row -> (row, frames)
PET_ROWS = {"idle": (0, 6), "running-right": (1, 8), "running-left": (2, 8), "waving": (3, 4), "jumping": (4, 5),
            "failed": (5, 8), "waiting": (6, 6), "running": (7, 6), "review": (8, 6)}
# which pet animation plays for each Mondesk expression; while talking it plays "running" (busy)
PET_FACES = {"neutral": "idle", "happy": "jumping", "thinking": "review", "worried": "failed",
             "surprised": "waving", "sleepy": "waiting", "talk_open": "running", "talk_closed": "running"}


class PackError(ValueError):
    pass


@dataclass
class Character:
    id: str
    name: str
    folder: Path
    faces: dict                      # face -> ("image", Path) | ("text", str)
    builtin: bool = False
    author: str = ""
    description: str = ""
    persona: str = ""
    manifest: dict = field(default_factory=dict)
    sheet: Path = None               # sprite sheet of an animated pack
    sprite: dict = field(default_factory=dict)   # face -> [row, frames]
    source: str = ""                 # "codex" for pets read from the Codex pets folder

    def face_info(self):
        """What the panel needs per face: an image version (cache-busting), the text, or the
        sprite row to animate. A sprite face wins over a still image of the same name."""
        out = {}
        for name, (kind, value) in self.faces.items():
            if kind == "text":
                out[name] = {"text": value}
            else:
                st = value.stat()
                out[name] = {"v": f"{int(st.st_mtime)}{st.st_size}"}
        if self.sheet:
            st = self.sheet.stat()
            s = self.manifest["sprite"]
            for name, (row, frames) in self.sprite.items():
                out[name] = {"sprite": {"v": f"{int(st.st_mtime)}{st.st_size}", "row": row, "frames": frames,
                                        "columns": s["columns"], "cell": s["cell"]}}
        return out

    def summary(self):
        return {"id": self.id, "name": self.name, "author": self.author, "description": self.description,
                "builtin": self.builtin, "source": self.source, "faces": self.face_info()}


def user_dir():
    from .companion import user_folder
    return user_folder() / "characters"


def codex_pets_dir():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "pets"


def is_image_name(value):
    return Path(value).suffix.lower() in IMAGE_TYPES


def slug(manifest):
    cid = str(manifest.get("id") or "").strip().lower()
    if ID_RE.match(cid):
        return cid
    base = re.sub(r"[^a-z0-9]+", "-", str(manifest.get("name") or "").lower()).strip("-")[:32]
    return base if ID_RE.match(base or "") else "character-" + hashlib.sha1(
        json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:8]


def _validate_sprite(sprite, has_file):
    if not isinstance(sprite, dict):
        raise PackError("sprite 必須是 JSON 物件")
    sheet = str(sprite.get("sheet") or "").strip()
    if not is_image_name(sheet) or sheet.lower().endswith(".svg") or not FILE_RE.match(sheet) or not has_file(sheet):
        raise PackError(f"sprite.sheet：找不到圖片 {sheet}")
    cols, cell = sprite.get("columns", 8), sprite.get("cell", [192, 208])
    if not (isinstance(cols, int) and 1 <= cols <= 32 and isinstance(cell, list) and len(cell) == 2
            and all(isinstance(n, int) and 8 <= n <= 1024 for n in cell)):
        raise PackError("sprite.columns／sprite.cell 不正確")
    faces = {}
    for face, value in (sprite.get("faces") or {}).items():
        if face not in FACE_NAMES:
            continue
        if not (isinstance(value, list) and len(value) == 2 and all(type(n) is int for n in value)
                and 0 <= value[0] < 64 and 1 <= value[1] <= cols):
            raise PackError(f"sprite.faces.{face} 必須是 [列, 張數]")
        faces[face] = value
    if not faces:
        raise PackError("sprite.faces 至少要有一個表情")
    return {"sheet": sheet, "columns": cols, "cell": cell, "faces": faces}


def validate(manifest, has_file):
    """Check a manifest; returns the cleaned copy. `has_file(name)` says whether the pack
    contains that file."""
    if not isinstance(manifest, dict):
        raise PackError("character.json 必須是 JSON 物件")
    fmt = manifest.get("format", FORMAT)
    if fmt != FORMAT:
        raise PackError(f"不支援的格式：{fmt}（需要 {FORMAT}）")
    name = str(manifest.get("name") or "").strip()
    if not name or len(name) > 40:
        raise PackError("name 必須是 1–40 個字")
    sprite = _validate_sprite(manifest["sprite"], has_file) if manifest.get("sprite") is not None else None
    faces = manifest.get("faces", {} if sprite else None)
    if not isinstance(faces, dict) or "neutral" not in faces and not (sprite and "neutral" in sprite["faces"]):
        raise PackError("faces 至少要有 neutral")
    clean = {}
    for face, value in faces.items():
        if face not in FACE_NAMES:
            continue  # unknown expressions are ignored, so newer packs still load
        if not isinstance(value, str) or not value.strip():
            raise PackError(f"faces.{face} 必須是檔名或文字")
        value = value.strip()
        if is_image_name(value):
            if not FILE_RE.match(value) or not has_file(value):
                raise PackError(f"faces.{face}：找不到圖片 {value}")
        elif len(value) > 12:
            raise PackError(f"faces.{face}：文字表情最多 12 個字元")
        clean[face] = value
    out = {"format": FORMAT, "name": name, "faces": clean}
    if sprite:
        out["sprite"] = sprite
    for key, limit in (("author", 60), ("description", 120), ("persona", 300)):
        if manifest.get(key):
            out[key] = str(manifest[key]).strip()[:limit]
    out["id"] = slug({**manifest, "name": name})
    return out


def pet_manifest(pet):
    """A Codex pet.json ({id, displayName, description, spritesheetPath}) as a character manifest."""
    if not isinstance(pet, dict):
        raise PackError("pet.json 必須是 JSON 物件")
    name = str(pet.get("displayName") or pet.get("name") or pet.get("id") or "").strip()[:40] or "Codex pet"
    return {"format": FORMAT, "id": str(pet.get("id") or ""), "name": name,
            "description": str(pet.get("description") or ""), "author": str(pet.get("author") or ""),
            "sprite": {"sheet": str(pet.get("spritesheetPath") or "spritesheet.webp").strip(), "columns": 8,
                       "cell": [192, 208], "faces": {f: list(PET_ROWS[a]) for f, a in PET_FACES.items()}}}


def _parse(text, what):
    try:
        return json.loads(text)
    except ValueError as e:
        raise PackError(f"{what} 不是有效的 JSON") from e


def _sheet_of(raw):
    return (raw.get("sprite") or {}).get("sheet") if isinstance(raw, dict) and isinstance(raw.get("sprite"), dict) else None


def load_folder(folder, builtin=False, codex=False):
    folder = Path(folder)
    if (folder / "character.json").is_file():
        raw = _parse((folder / "character.json").read_text(encoding="utf-8-sig"), "character.json")
    elif (folder / "pet.json").is_file():
        raw = pet_manifest(_parse((folder / "pet.json").read_text(encoding="utf-8-sig"), "pet.json"))
    else:  # a plain folder of face images
        found = {f: p.name for f in FACE_NAMES for p in sorted(folder.glob(f + ".*")) if p.suffix.lower() in IMAGE_TYPES}
        if "neutral" not in found:
            raise PackError("資料夾裡沒有 character.json、pet.json 或 neutral 圖片")
        raw = {"name": folder.name, "id": folder.name.lower(), "faces": found}
    sheet = _sheet_of(raw)
    m = validate(raw, lambda n: (folder / n).is_file()
                 and (folder / n).stat().st_size <= (MAX_SHEET if n == sheet else MAX_IMAGE))
    faces = {f: ("image", folder / v) if is_image_name(v) else ("text", v) for f, v in m["faces"].items()}
    cid = folder.name if builtin else (CODEX_PREFIX + m["id"])[:40] if codex else m["id"]
    return Character(id=cid, name=m["name"], folder=folder, faces=faces, builtin=builtin,
                     author=m.get("author", ""), description=m.get("description", ""),
                     persona=m.get("persona", ""), manifest=m,
                     sheet=folder / m["sprite"]["sheet"] if "sprite" in m else None,
                     sprite=dict(m["sprite"]["faces"]) if "sprite" in m else {},
                     source="codex" if codex else "")


def _folders():
    """(folder, builtin, codex) for every place a pack can live, in listing order."""
    def subdirs(d):
        try:
            return sorted(p for p in d.iterdir() if p.is_dir() and not p.name.endswith(".importing"))
        except OSError:
            return []
    return [*((p, True, False) for p in subdirs(BUILTIN_DIR)), *((p, False, False) for p in subdirs(user_dir())),
            *((p, False, True) for p in subdirs(codex_pets_dir()))]


def list_characters():
    """Built-in packs first, then the user's, then Codex pets. Broken user packs are listed
    with their error; broken Codex pets are skipped (they belong to Codex)."""
    out, seen = [], set()
    for folder, builtin, codex in _folders():
        try:
            c = load_folder(folder, builtin, codex)
            if c.id in seen:
                continue
            seen.add(c.id)
            out.append(c.summary())
        except (PackError, OSError) as e:
            if not builtin and not codex:
                out.append({"id": folder.name, "name": folder.name, "builtin": False, "error": str(e), "faces": {}})
    return out


def find(cid):
    """The pack with this id, or the default one."""
    cid = str(cid or "")
    if ID_RE.match(cid):
        for folder, builtin, codex in ((BUILTIN_DIR / cid, True, False), (user_dir() / cid, False, False)):
            if folder.is_dir():
                try:
                    return load_folder(folder, builtin, codex)
                except (PackError, OSError):
                    break
        # imported packs are stored by id and Codex pets by their own id, but tolerate renamed folders
        for folder, builtin, codex in _folders():
            if builtin:
                continue
            try:
                c = load_folder(folder, builtin, codex)
                if c.id == cid:
                    return c
            except (PackError, OSError):
                continue
    return load_folder(BUILTIN_DIR / DEFAULT_ID, True)


def face_file(cid, face):
    """(bytes, mime) of an image face or of the sprite sheet ("sheet"), for
    /api/companion/character/<id>/<face>."""
    if (face not in FACE_NAMES and face != SHEET) or not ID_RE.match(str(cid or "")):
        return None
    c = find(cid)
    if c.id != cid:
        return None
    if face == SHEET:
        return (c.sheet.read_bytes(), IMAGE_TYPES[c.sheet.suffix.lower()]) if c.sheet else None
    kind, value = c.faces.get(face, (None, None))
    if kind != "image":
        return None
    return value.read_bytes(), IMAGE_TYPES[value.suffix.lower()]


def import_package(data, filename=""):
    """Install a .zip pack (folder with character.json + images, or a Codex pet folder with
    pet.json + spritesheet.webp) or a bare character.json (text/emoji faces only). Returns the
    installed summary."""
    if not data or len(data) > MAX_PACKAGE:
        raise PackError("檔案是空的或超過 10 MB")
    files = {}
    if data[:2] == b"PK":
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as e:
            raise PackError("不是有效的 zip 檔") from e
        infos = [i for i in zf.infolist() if not i.is_dir()]
        manifests = [i for i in infos if Path(i.filename).name == "character.json" and i.filename.count("/") <= 1]
        pets = [i for i in infos if Path(i.filename).name == "pet.json" and i.filename.count("/") <= 1]
        if len(manifests) > 1 or not manifests and len(pets) != 1:
            raise PackError("zip 裡要剛好有一個 character.json 或 Codex 的 pet.json（放在最外層或第一層資料夾）")
        top = manifests[0] if manifests else pets[0]
        name = Path(top.filename).name
        prefix = top.filename[:-len(name)]
        total = 0
        for info in infos:
            if not info.filename.startswith(prefix):
                continue
            rel = info.filename[len(prefix):]
            if "/" in rel or "\\" in rel or not FILE_RE.match(rel):
                continue  # only flat files next to the manifest; never paths
            if rel != name and Path(rel).suffix.lower() not in IMAGE_TYPES:
                continue
            if info.file_size > (64 * 1024 if rel == name else MAX_SHEET):
                raise PackError(f"{rel} 太大")
            total += info.file_size
            if total > MAX_UNPACKED:
                raise PackError("解壓後超過 24 MB")
            files[rel] = info
        try:
            raw = json.loads(zf.read(files[name]).decode("utf-8-sig"))
        except (KeyError, ValueError, UnicodeDecodeError) as e:
            raise PackError(f"{name} 不是有效的 JSON") from e
        if name == "pet.json":
            raw = pet_manifest(raw)
        sheet = _sheet_of(raw)
        manifest = validate(raw, lambda n: n in files and files[n].file_size <= (MAX_SHEET if n == sheet else MAX_IMAGE))
        wanted = {v for v in manifest["faces"].values() if is_image_name(v)}
        if "sprite" in manifest:
            wanted.add(manifest["sprite"]["sheet"])
        blobs = {v: zf.read(files[v]) for v in wanted}
    else:
        try:
            raw = json.loads(data.decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError) as e:
            raise PackError("請匯入 .zip 角色包（含 Codex pet）或 character.json") from e
        if isinstance(raw, dict) and "spritesheetPath" in raw:
            raise PackError("Codex pet 要連同 spritesheet.webp 一起壓成 zip 再匯入")
        manifest = validate(raw, lambda n: False)  # a bare json can't carry images
        blobs = {}
    for name, blob in blobs.items():
        if Path(name).suffix.lower() != ".svg" and not _looks_like_image(blob):
            raise PackError(f"{name} 不是圖片檔")
    if (BUILTIN_DIR / manifest["id"]).is_dir():
        manifest["id"] += "-custom"
    target = user_dir() / manifest["id"]
    tmp = target.with_name(target.name + ".importing")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for name, blob in blobs.items():
        (tmp / name).write_bytes(blob)
    (tmp / "character.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.rmtree(target, ignore_errors=True)
    tmp.rename(target)
    return load_folder(target).summary()


def _looks_like_image(blob):
    return (blob[:8] == b"\x89PNG\r\n\x1a\n" or blob[:3] == b"\xff\xd8\xff" or blob[:6] in (b"GIF87a", b"GIF89a")
            or blob[:4] == b"RIFF" and blob[8:12] == b"WEBP")


def export_package(cid):
    """A .zip of one pack, in the same format import_package reads."""
    c = find(cid)
    if c.id != cid:
        raise PackError("找不到這個角色")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = {**c.manifest, "id": c.id}
        zf.writestr(f"{c.id}/character.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        images = {v for kind, v in c.faces.values() if kind == "image"} | ({c.sheet} if c.sheet else set())
        for value in sorted(images):
            zf.write(value, f"{c.id}/{value.name}")
    return buf.getvalue(), f"{c.id}.zip"


def delete_package(cid):
    folder = user_dir() / str(cid)
    if not ID_RE.match(str(cid or "")) or not folder.is_dir():
        raise PackError("只能刪除匯入的角色（Codex 的寵物請在 Codex 裡移除）")
    shutil.rmtree(folder)
