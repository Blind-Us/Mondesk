"""Module contract.

Every file in this package exposes `class Module(BaseModule)`. The hub calls
`start()` once, then `poll()` every `interval` seconds. `poll()` returns a
JSON-able dict; put `_status` in it ("ok" / "idle" / "offline" / "error") to
drive the card's status dot. To add a new source, drop a file here and add an
entry with `"type": "<filename>"` to config.json.
"""


class BaseModule:
    type = "base"
    default_interval = 5

    def __init__(self, spec):
        self.spec = spec
        self.id = spec.get("id", self.type)
        self.title = spec.get("title", self.type)
        self.interval = spec.get("interval", self.default_interval)

    def start(self):
        pass

    def poll(self):
        return {}

    def stop(self):
        """Called when settings are saved and the module is replaced."""
