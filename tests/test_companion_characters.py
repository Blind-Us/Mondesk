import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from modules import companion_characters as chars
from modules.companion_brain import build_system_prompt

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
WEBP = b"RIFF\0\0\0\0WEBP" + b"\0" * 32


def pack(manifest, files=None, folder="sunny/"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(folder + "character.json", json.dumps(manifest, ensure_ascii=False))
        for name, blob in (files or {}).items():
            zf.writestr(name if name.startswith("..") else folder + name, blob)
    return buf.getvalue()


class CharacterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        p = patch.object(chars, "user_dir", return_value=self.tmp)
        p.start()
        self.addCleanup(p.stop)
        self.codex = Path(tempfile.mkdtemp())
        p = patch.object(chars, "codex_pets_dir", return_value=self.codex)
        p.start()
        self.addCleanup(p.stop)

    def test_builtin_packs(self):
        ids = [c["id"] for c in chars.list_characters()]
        self.assertEqual(ids[:2], ["emoji", "kid"])
        emoji = chars.find("emoji")
        self.assertEqual(emoji.faces["happy"], ("text", "😄"))
        self.assertNotIn("talk_open", emoji.faces)  # bounces instead of moving its mouth
        self.assertEqual(chars.face_file("kid", "happy")[1], "image/svg+xml")
        self.assertIsNone(chars.face_file("emoji", "happy"))  # text faces have no file

    def test_import_zip_then_export_round_trip(self):
        data = pack({"format": chars.FORMAT, "name": "Sunny", "author": "me", "persona": "開朗",
                     "faces": {"neutral": "n.png", "happy": "😄", "angry": "x.png"}}, {"n.png": PNG})
        got = chars.import_package(data)
        self.assertEqual((got["id"], got["faces"]["happy"]), ("sunny", {"text": "😄"}))
        self.assertEqual(chars.face_file("sunny", "neutral"), (PNG, "image/png"))
        body, name = chars.export_package("sunny")
        self.assertEqual(name, "sunny.zip")
        chars.delete_package("sunny")
        self.assertEqual(chars.import_package(body)["name"], "Sunny")  # an export imports again
        self.assertEqual(chars.find("sunny").persona, "開朗")

    def test_bare_json_with_emoji_faces(self):
        got = chars.import_package(json.dumps({"name": "貓貓", "faces": {"neutral": "🐱", "happy": "😸"}}).encode())
        self.assertTrue(got["id"].startswith("character-"))  # Chinese-only name: hashed id

    def test_rejects_unsafe_or_broken_packs(self):
        bad = [
            (b"", "空的"),
            (b"PK\x03\x04garbage", "zip"),
            (pack({"name": "x", "faces": {"happy": "😄"}}), "neutral"),
            (pack({"name": "x", "faces": {"neutral": "missing.png"}}), "找不到圖片"),
            (pack({"name": "x", "faces": {"neutral": "n.png"}}, {"../n.png": PNG}), "找不到圖片"),  # traversal ignored
            (pack({"name": "x", "faces": {"neutral": "n.png"}}, {"n.png": b"<html>not an image"}), "不是圖片"),
            (pack({"name": "x", "faces": {"neutral": "a very long text face"}}), "12"),
            (pack({"format": "other/2", "name": "x", "faces": {"neutral": "🙂"}}), "不支援的格式"),
            (json.dumps({"name": "x", "faces": {"neutral": "n.png"}}).encode(), "找不到圖片"),  # json has no images
        ]
        for data, msg in bad:
            with self.assertRaisesRegex(chars.PackError, msg):
                chars.import_package(data)
        self.assertEqual(list(self.tmp.iterdir()), [])  # nothing half-installed
        with self.assertRaises(chars.PackError):
            chars.delete_package("emoji")  # built-in packs stay

    def test_builtin_ids_are_not_overwritten(self):
        got = chars.import_package(json.dumps({"id": "emoji", "name": "Mine", "faces": {"neutral": "🙃"}}).encode())
        self.assertEqual(got["id"], "emoji-custom")
        self.assertEqual(chars.find("emoji").faces["neutral"], ("text", "🙂"))

    def test_plain_folder_of_images_works(self):
        (self.tmp / "gen").mkdir()
        (self.tmp / "gen" / "neutral.png").write_bytes(PNG)
        (self.tmp / "gen" / "happy.webp").write_bytes(b"RIFF\0\0\0\0WEBP")
        self.assertEqual(sorted(chars.find("gen").faces), ["happy", "neutral"])

    def test_codex_pet_zip_imports_as_an_animated_pack(self):
        pet = {"id": "terminal-ghost", "displayName": "Terminal Ghost", "description": "A tiny CLI ghost.",
               "spritesheetPath": "spritesheet.webp"}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("terminal-ghost/pet.json", json.dumps(pet))
            zf.writestr("terminal-ghost/spritesheet.webp", WEBP)
        got = chars.import_package(buf.getvalue())
        self.assertEqual((got["id"], got["name"]), ("terminal-ghost", "Terminal Ghost"))
        neutral, worried = got["faces"]["neutral"]["sprite"], got["faces"]["worried"]["sprite"]
        self.assertEqual((neutral["row"], neutral["frames"], neutral["columns"], neutral["cell"]), (0, 6, 8, [192, 208]))
        self.assertEqual((worried["row"], worried["frames"]), (5, 8))  # the "failed" row
        self.assertEqual(chars.face_file("terminal-ghost", "sheet"), (WEBP, "image/webp"))
        self.assertIsNone(chars.face_file("emoji", "sheet"))
        body, _ = chars.export_package("terminal-ghost")  # exports as a Mondesk pack that imports again
        chars.delete_package("terminal-ghost")
        self.assertIn("sprite", chars.find(chars.import_package(body)["id"]).manifest)
        with self.assertRaisesRegex(chars.PackError, "zip"):
            chars.import_package(json.dumps(pet).encode())  # pet.json alone has no sheet

    def test_installed_codex_pets_show_up_by_themselves(self):
        (self.codex / "mimi").mkdir()
        (self.codex / "mimi" / "pet.json").write_text(json.dumps({"id": "mimi", "displayName": "Mimi",
                                                                  "spritesheetPath": "spritesheet.webp"}))
        (self.codex / "mimi" / "spritesheet.webp").write_bytes(WEBP)
        (self.codex / "broken").mkdir()  # no pet.json: skipped, not listed as an error
        listed = {c["id"]: c for c in chars.list_characters()}
        self.assertEqual((listed["codex-mimi"]["name"], listed["codex-mimi"]["source"]), ("Mimi", "codex"))
        self.assertNotIn("broken", listed)
        self.assertEqual(chars.find("codex-mimi").sheet.name, "spritesheet.webp")
        with self.assertRaisesRegex(chars.PackError, "Codex"):
            chars.delete_package("codex-mimi")  # never deletes Codex's own files

    def test_sprite_manifest_is_validated(self):
        base = {"name": "s", "sprite": {"sheet": "s.png", "faces": {"neutral": [0, 4]}}}
        self.assertEqual(chars.import_package(pack(base, {"s.png": PNG}))["faces"]["neutral"]["sprite"]["frames"], 4)
        for sprite, msg in (({"sheet": "s.svg", "faces": {"neutral": [0, 1]}}, "sheet"),
                            ({"sheet": "s.png", "faces": {"neutral": [0, 99]}}, "張數"),
                            ({"sheet": "s.png", "faces": {"happy": [0, 1]}}, "neutral")):
            with self.assertRaisesRegex(chars.PackError, msg):
                chars.import_package(pack({"name": "t", "sprite": sprite}, {"s.png": PNG, "s.svg": b"<svg/>"}))

    def test_persona_goes_into_the_prompt_but_rules_stay_first(self):
        prompt = build_system_prompt("Sunny", "愛吐槽  的小太陽\n" + "x" * 500)
        self.assertTrue(prompt.startswith("你是「Sunny」"))
        self.assertIn("愛吐槽 的小太陽", prompt)
        self.assertLess(len(prompt), len(build_system_prompt("Sunny")) + 400)

    def test_http_routes(self):
        import server
        app = type("App", (), {})()
        app.hub = type("Hub", (), {"config": {}})()
        http = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(app))
        threading.Thread(target=http.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{http.server_port}/api/companion/"
        try:
            listed = json.load(urllib.request.urlopen(base + "characters"))
            self.assertIn("emoji", [c["id"] for c in listed["characters"]])
            r = urllib.request.urlopen(base + "character/kid/happy")
            self.assertIn("sandbox", r.headers["Content-Security-Policy"])  # SVGs never run scripts here
            req = urllib.request.Request(base + "import", data=json.dumps({"name": "Test", "faces": {"neutral": "🙂"}}).encode())
            with self.assertRaises(urllib.error.HTTPError) as no_header:  # writes need Mondesk's own page
                urllib.request.urlopen(req)
            self.assertEqual(no_header.exception.code, 403)
            req.add_header("X-DeskMon", "1")
            self.assertEqual(json.load(urllib.request.urlopen(req))["character"]["id"], "test")
            self.assertEqual(urllib.request.urlopen(base + "export/test").headers["Content-Type"], "application/zip")
        finally:
            http.shutdown()
            http.server_close()


class SystemModuleTests(unittest.TestCase):
    def test_volume_and_brightness_actions(self):
        from modules.system import Module

        class Audio:
            vol, muted = 40, True
            def get(self): return self.vol, self.muted
            def set(self, v): self.vol = int(v)
            def mute(self, on): self.muted = on

        class Bright:
            def __init__(self): self.calls = []
            def read(self): return [{"index": 0, "name": "螢幕 1", "value": 60}]
            def set(self, i, v): self.calls.append((i, v))

        m = Module({"id": "system", "type": "system"})
        m.audio, m.bright = Audio(), Bright()
        self.assertEqual(m.poll()["volume"], 40)
        d = m.action("set_volume", value=55)
        self.assertEqual((d["volume"], d["muted"]), (55, False))  # raising the volume unmutes
        self.assertTrue(m.action("toggle_mute")["muted"])
        self.assertEqual(m.action("set_brightness", value=30, index=0)["monitors"][0]["value"], 30)
        self.assertEqual(m.bright.calls, [(0, 30.0)])
        with self.assertRaises(ValueError):
            m.action("reboot")

    def test_unavailable_audio_is_reported_not_raised(self):
        from modules.system import Module

        class Broken:
            def get(self): raise OSError("no device")

        m = Module({"id": "system", "type": "system"})
        m.audio = Broken()
        m.bright = type("B", (), {"read": lambda self: []})()
        d = m.poll()
        self.assertEqual((d["_status"], d["volume"]), ("offline", None))
        self.assertIn("無法讀取音量", d["audio_error"])


if __name__ == "__main__":
    unittest.main()
