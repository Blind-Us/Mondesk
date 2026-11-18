"""Companion brain: what the character can see (tools) and how it decides what to say.

Three interchangeable brains share one contract, `respond(event, world) -> Reply`:
  * AnthropicBrain - Claude through the Messages API with tool use and structured output
  * OllamaBrain    - a local model through Ollama's /api/chat, for comparison
  * RuleBrain      - fixed templates, no model call (also the fallback when a call fails or
                     the hourly cap is reached, so the character never goes silent)
"""
import json
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime

# The six expressions the model may choose. The two talking frames (mouth open / closed)
# are drawn by the panel while a line is being "spoken", so the model never picks them.
EMOTIONS = ("neutral", "happy", "thinking", "worried", "surprised", "sleepy")
FACE_NAMES = EMOTIONS + ("talk_open", "talk_closed")

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "line": {"type": "string", "description": "對使用者說的話：繁體中文、一到兩句"},
        "emotion": {"type": "string", "enum": list(EMOTIONS)},
    },
    "required": ["line", "emotion"],
    "additionalProperties": False,
}

MAX_LINE = 60  # characters; the bubble on the 7 cm screen fits about two lines of this

SYSTEM_TEMPLATE = """你是「{name}」，住在使用者桌上一塊 7 公分小螢幕裡的卡通角色，個性像坐在旁邊的同事：友善、輕鬆、話不多。

使用者平常一邊寫程式（用 Codex 和 Claude Code），一邊用 Bambu Lab 3D 列印機印東西、聽音樂。Mondesk 會在發生事件時叫你出來說一句話。

說話規則：
- 只用繁體中文，一到兩句話，總長不超過 40 個字。
- 口吻自然口語，像同事隨口提醒；不客套、不說教、不用表情符號、不用 Markdown、不加引號。
- 只根據工具查到的資料發言。不要猜測或編造任何數字、檔名、歌名、時間；查不到的就不要提。
- 開口前先用工具確認和這次事件有關的資料；和事件無關的工具不用查。
- 時間說成「大約 20 分鐘」「1 小時後」這類口語，百分比取整數。

表情 emotion 只能選一個：
- neutral：平常、單純報告
- happy：好消息、完成了
- thinking：資訊不完整、在整理狀況
- worried：失敗、額度快滿、需要注意
- surprised：意外的變化
- sleepy：工作太久、很晚了、提醒休息

最後只輸出 JSON：{{"line": "要說的話", "emotion": "表情"}}。"""


def build_system_prompt(name="Mondesk Companion", persona=""):
    """The character pack supplies its name and (optionally) a personality; the rules stay."""
    prompt = SYSTEM_TEMPLATE.format(name=name)
    if persona:
        prompt += ("\n\n角色個性（使用者選的角色設定，只影響語氣和用詞，不改變上面的規則）："
                   + " ".join(str(persona).split())[:300])
    return prompt


SYSTEM_PROMPT = build_system_prompt()

_NO_INPUT = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
TOOLS = [
    {"name": "get_printer_status", "input_schema": _NO_INPUT,
     "description": "查詢 3D 列印機目前狀態：是否連線、階段（列印中／完成／失敗…）、檔名、進度百分比、剩餘分鐘、預計完成時間、噴頭與熱床溫度、錯誤碼。"},
    {"name": "get_now_playing", "input_schema": _NO_INPUT,
     "description": "查詢目前正在播放的歌曲或影片：歌名、歌手、專輯、來源（Apple Music、YouTube…）、播放進度。"},
    {"name": "get_ai_quota", "input_schema": _NO_INPUT,
     "description": "查詢 Codex 與 Claude 的用量：今天用了多少 tokens，以及 5 小時與 7 天額度已用百分比和距離重置還有多久。"},
    {"name": "get_weather", "input_schema": _NO_INPUT,
     "description": "查詢使用者所在地的天氣：現在氣溫與體感、天氣狀況、今天最高最低溫、今天降雨機率，以及接下來幾小時內會不會下雨。"},
]

EVENT_HINTS = {
    "print_finished": "列印剛完成。可以開心地說一聲，必要時提醒等熱床降溫再拿。",
    "print_failed": "列印失敗、被停止或因錯誤暫停。用擔心的語氣提醒使用者去看一下列印機。",
    "quota_high": "某個 AI 工具的額度用量超過 {threshold}%。提醒使用者剩多少、多久後重置，語氣擔心但不要嚇人。",
    "song_change": "剛換歌。偶爾聊一句這首歌就好，輕鬆一點；不知道的事不要亂講。",
    "long_work": "使用者已經連續工作約 {work}。提醒休息一下，表情可以是想睡。",
    "timer_done": "使用者設定的倒數計時剛結束。簡短提醒時間到了。",
    "rain_soon": "接下來幾小時內可能下雨。查一下天氣，提醒使用者帶傘或收衣服，不要誇大。",
    "tap": "使用者點了你的臉，想知道現在狀況。查一下各項資料，用一兩句話摘要最值得知道的事。",
}


def fmt_minutes(minutes):
    if minutes is None:
        return None
    minutes = max(0, int(round(minutes)))
    if minutes < 60:
        return f"{minutes} 分鐘"
    h, m = divmod(minutes, 60)
    if h >= 24:
        return f"{h // 24} 天 {h % 24} 小時"
    return f"{h} 小時" + (f" {m} 分" if m else "")


def fmt_clock(seconds):
    if not seconds or seconds < 0:
        return "0:00"
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


# ---------------------------------------------------------------- what the character sees
class World:
    """Read-only view of Mondesk's modules for one event, exposed as the model's tools.

    `scenario` replaces parts of the real data (manual test triggers in the settings page),
    so the agent can be tried on "print finished" without a print actually finishing."""

    def __init__(self, modules, work_minutes=0, now=None, scenario=None):
        self.modules = modules
        self.work_minutes = work_minutes
        self.now = now or time.time()
        self.scenario = scenario or {}
        self.called = []

    def _first(self, kind):
        return next((m for m in self.modules if m.get("type") == kind), None)

    def call(self, name, _input=None):
        self.called.append(name)
        fn = {"get_printer_status": self.printer, "get_now_playing": self.now_playing,
              "get_ai_quota": self.ai_quota, "get_weather": self.weather}.get(name)
        if not fn:
            return {"error": f"沒有這個工具：{name}"}
        return fn()

    def printer(self):
        if "printer" in self.scenario:
            return self.scenario["printer"]
        m = self._first("bambu")
        if not m:
            return {"available": False, "reason": "沒有設定印表機"}
        d = m.get("data") or {}
        if not d.get("stage"):
            return {"available": True, "connected": False, "message": d.get("message") or "印表機未連線"}
        remain = d.get("remaining_min")
        out = {
            "available": True, "connected": not d.get("stale"),
            "stage": d.get("stage"), "stage_label": d.get("stage_label"),
            "file": d.get("file") or None, "progress_percent": d.get("progress"),
            "remaining_minutes": remain,
            "finish_time": datetime.fromtimestamp(d["eta"]).strftime("%H:%M") if d.get("eta") and remain else None,
            "layer": f"{d.get('layer')}/{d.get('total_layers')}" if d.get("total_layers") else None,
            "nozzle_c": d.get("nozzle"), "nozzle_target_c": d.get("nozzle_target"),
            "bed_c": d.get("bed"), "bed_target_c": d.get("bed_target"),
            "failed": d.get("stage") == "FAILED" or bool(d.get("print_error")),
            "error_code": d.get("print_error") or None,
        }
        return {k: v for k, v in out.items() if v is not None}

    def now_playing(self):
        if "music" in self.scenario:
            return self.scenario["music"]
        m = self._first("media")
        d = (m or {}).get("data") or {}
        if not d.get("title"):
            return {"playing": False, "reason": "目前沒有播放" if m else "沒有設定播放模組"}
        pos = d.get("position") or 0
        if d.get("playing") and d.get("sampled"):
            pos += max(0, self.now - d["sampled"])
        dur = d.get("duration") or 0
        out = {"playing": bool(d.get("playing")), "title": d.get("title"), "artist": d.get("artist") or None,
               "album": d.get("album") or None, "source": d.get("source") or None,
               "is_video": bool(d.get("video")) or None,
               "position": fmt_clock(min(pos, dur) if dur else pos), "duration": fmt_clock(dur) if dur else None,
               "progress_percent": round(min(pos, dur) / dur * 100) if dur else None}
        return {k: v for k, v in out.items() if v is not None}

    def ai_quota(self):
        if "quota" in self.scenario:
            return {"tools": self.scenario["quota"]}
        from .companion_events import quota_windows
        tools = []
        for m in self.modules:
            if m.get("type") != "tokens":
                continue
            d = m.get("data") or {}
            today = d.get("today") or {}
            entry = {"name": m.get("title") or d.get("provider"), "plan": d.get("plan") or None,
                     "today_tokens": (today.get("input", 0) + today.get("output", 0)) if today else None,
                     "windows": [{"label": {"5h": "5 小時", "7d": "7 天"}.get(label, label),
                                  "used_percent": round(pct),
                                  "resets_in": fmt_minutes((resets - self.now) / 60) if resets else None}
                                 for label, pct, resets in quota_windows(d)]}
            tools.append({k: v for k, v in entry.items() if v not in (None, [])})
        return {"tools": tools} if tools else {"tools": [], "reason": "沒有 AI 用量資料"}


    def weather(self):
        if "weather" in self.scenario:
            return self.scenario["weather"]
        m = self._first("weather")
        d = (m or {}).get("data") or {}
        if d.get("temp") is None:
            return {"available": False, "reason": d.get("message") or ("天氣資料尚未取得" if m else "沒有設定天氣")}
        soon = d.get("rain_soon") or {}
        out = {"available": True, "place": d.get("place") or None, "condition": d.get("label"),
               "temperature_c": d.get("temp"), "feels_like_c": d.get("feels"),
               "high_c": d.get("high"), "low_c": d.get("low"),
               "rain_probability_today_percent": d.get("rain_today"),
               "rain_within_hours": soon.get("in_hours"), "rain_probability_percent": soon.get("probability"),
               "data_is_old": True if d.get("stale") else None}
        return {k: v for k, v in out.items() if v is not None}


# Manual test triggers: fake data for one event, merged over the real data.
SCENARIOS = {
    "print_finished": {"printer": {"available": True, "connected": True, "stage": "FINISH", "stage_label": "已完成",
                                   "file": "貓咪手機架", "progress_percent": 100, "remaining_minutes": 0,
                                   "nozzle_c": 96, "bed_c": 58, "bed_target_c": 0, "failed": False}},
    "print_failed": {"printer": {"available": True, "connected": True, "stage": "FAILED", "stage_label": "失敗",
                                 "file": "齒輪盒蓋", "progress_percent": 37, "failed": True, "error_code": 50348044}},
    "quota_high": {"quota": [{"name": "Claude", "plan": "max",
                              "windows": [{"label": "5 小時", "used_percent": 86, "resets_in": "1 小時 12 分"},
                                          {"label": "7 天", "used_percent": 41, "resets_in": "3 天 5 小時"}]}]},
    "song_change": {"music": {"playing": True, "title": "晴天", "artist": "周杰倫", "album": "葉惠美",
                              "source": "Apple Music", "position": "0:05", "duration": "4:29", "progress_percent": 2}},
    "long_work": {"work_minutes": 135},
    "timer_done": {},
    "rain_soon": {"weather": {"available": True, "place": "台北", "condition": "多雲", "temperature_c": 24,
                              "high_c": 27, "low_c": 21, "rain_probability_today_percent": 80,
                              "rain_within_hours": 2, "rain_probability_percent": 70}},
    "tap": {"printer": {"available": True, "connected": True, "stage": "RUNNING", "stage_label": "列印中",
                        "file": "貓咪手機架", "progress_percent": 64, "remaining_minutes": 38, "finish_time": "15:42",
                        "nozzle_c": 220, "bed_c": 60, "failed": False},
            "quota": [{"name": "Codex", "windows": [{"label": "5 小時", "used_percent": 23, "resets_in": "3 小時 40 分"}]},
                      {"name": "Claude", "windows": [{"label": "5 小時", "used_percent": 57, "resets_in": "2 小時 5 分"}]}]},
}

SIMULATED_DETAIL = {
    "print_finished": {"file": "貓咪手機架", "from": "RUNNING", "to": "FINISH"},
    "print_failed": {"file": "齒輪盒蓋", "from": "RUNNING", "to": "FAILED", "reason": "failed"},
    "quota_high": {"provider": "claude", "title": "Claude", "window": "5h", "used_percent": 86},
    "song_change": {"title": "晴天", "artist": "周杰倫"},
    "long_work": {"minutes": 135},
    "timer_done": {},
    "rain_soon": {"place": "台北", "in_hours": 2, "probability": 70},
    "tap": {},
}


def event_prompt(event, world, quota_threshold=80):
    now = datetime.fromtimestamp(world.now)
    weekday = "一二三四五六日"[now.weekday()]
    work = world.scenario.get("work_minutes", world.work_minutes)
    hint = EVENT_HINTS.get(event.name, "").format(threshold=f"{quota_threshold:g}", work=fmt_minutes(work) or "很久")
    detail = {k: v for k, v in event.detail.items() if v not in (None, "")}
    lines = [f"事件：{event.label}（{event.name}）", f"說明：{hint}",
             f"現在時間：{now:%Y-%m-%d} 週{weekday} {now:%H:%M}",
             f"使用者已連續工作：{fmt_minutes(work) if work else '不到 1 分鐘或剛休息過'}"]
    if detail:
        lines.append("事件細節：" + json.dumps(detail, ensure_ascii=False))
    return "\n".join(lines)


# ---------------------------------------------------------------- replies
@dataclass
class Reply:
    line: str
    emotion: str
    via: str                        # "claude-opus-5-5", "ollama:qwen3:8b", "rule"
    tools: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    served_by: str = None           # model that actually answered (server-side fallback)


class BrainError(RuntimeError):
    pass


def clean_line(text):
    text = " ".join(str(text or "").split()).strip("「」\"' ")
    if len(text) > MAX_LINE:
        cut = max(text.rfind(p, 0, MAX_LINE) for p in "。！？!?")
        text = text[:cut + 1] if cut >= MAX_LINE // 2 else text[:MAX_LINE - 1] + "…"
    return text


def parse_reply(text):
    """Structured output already guarantees the shape; still validate before it reaches the
    screen (local models, truncated responses)."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError) as e:
        raise BrainError(f"回應不是 JSON：{str(text)[:80]}") from e
    if not isinstance(data, dict):
        raise BrainError("回應格式錯誤")
    line = clean_line(data.get("line"))
    if not line:
        raise BrainError("回應沒有台詞")
    emotion = data.get("emotion") if data.get("emotion") in EMOTIONS else "neutral"
    return line, emotion


# ---------------------------------------------------------------- brains
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5")
MAX_TOOL_TURNS = 5


class AnthropicBrain:
    """Claude via the official SDK: manual tool loop (capped, so one event can't run up the
    bill), JSON-schema structured output, low effort for quick replies."""

    def __init__(self, model="claude-opus-5-5", effort="low", api_key=None, fallbacks=True,
                 timeout=45, client=None, quota_threshold=80, system=SYSTEM_PROMPT):
        self.model = model
        self.effort = effort
        self.api_key = api_key or None
        self.fallbacks = fallbacks and model in FALLBACK_MODELS
        self.timeout = timeout
        self._client = client
        self.quota_threshold = quota_threshold
        self.system = system

    @property
    def name(self):
        return self.model

    def client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as e:
                raise BrainError("缺少套件：pip install anthropic") from e
            # api_key=None lets the SDK use ANTHROPIC_API_KEY / an `ant auth login` profile
            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout, max_retries=1)
        return self._client

    def _create(self, messages):
        params = dict(
            model=self.model, max_tokens=8000, system=self.system, tools=TOOLS, messages=messages,
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
            cache_control={"type": "ephemeral"},  # the tool loop re-sends the same prefix
        )
        client = self.client()
        if self.fallbacks:
            # if a safety classifier declines, the API retries on a fallback model in the same call
            return client.beta.messages.create(**params, betas=[FALLBACK_BETA], fallbacks="default")
        return client.messages.create(**params)

    def respond(self, event, world):
        try:
            import anthropic
        except ImportError as e:
            if self._client is None:
                raise BrainError("缺少套件：pip install anthropic") from e
            anthropic = None  # an injected client (tests, other SDK builds) needs no package
        messages = [{"role": "user", "content": event_prompt(event, world, self.quota_threshold)}]
        usage = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0,
                 "cache_read_input_tokens": 0, "requests": 0}
        try:
            for _ in range(MAX_TOOL_TURNS):
                resp = self._create(messages)
                usage["requests"] += 1
                for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
                    usage[k] += getattr(resp.usage, k, 0) or 0
                if resp.stop_reason == "refusal":
                    raise BrainError("模型拒絕回答")
                if resp.stop_reason == "max_tokens":
                    raise BrainError("回應被截斷")
                if resp.stop_reason in ("tool_use", "pause_turn"):
                    messages.append({"role": "assistant", "content": resp.content})
                    calls = [b for b in resp.content if b.type == "tool_use"]
                    if calls:  # all results go back in one user message
                        messages.append({"role": "user", "content": [
                            {"type": "tool_result", "tool_use_id": b.id,
                             "content": json.dumps(world.call(b.name, b.input), ensure_ascii=False)}
                            for b in calls]})
                    continue
                text = next((b.text for b in resp.content if b.type == "text"), None)
                line, emotion = parse_reply(text)
                return Reply(line, emotion, via=self.model, tools=list(world.called), usage=usage,
                             served_by=getattr(resp, "model", None))
        except BrainError:
            raise
        except Exception as e:
            message = _sdk_error(anthropic, e)
            if message is None:
                raise
            raise BrainError(message) from e
        raise BrainError("工具呼叫次數過多")


def _sdk_error(sdk, e):
    """A short Chinese reason for an Anthropic SDK error, or None if it isn't one."""
    if sdk is None:
        return None
    for kind, message in (("AuthenticationError", "API 金鑰無效或未設定"), ("PermissionDeniedError", "API 金鑰沒有權限"),
                          ("RateLimitError", "API 請求太頻繁，稍後再試"), ("APIConnectionError", "連不到 Anthropic API")):
        if isinstance(e, getattr(sdk, kind)):
            return message
    if isinstance(e, sdk.APIStatusError):
        return f"API 錯誤 {e.status_code}"
    if isinstance(e, sdk.AnthropicError):  # e.g. no credentials found at all
        return "尚未設定 API 金鑰"
    return None


class OllamaBrain:
    """A local model through Ollama (https://ollama.com) for the speed / quality / cost
    comparison. Tools first, then one structured-output call if the reply isn't valid JSON."""

    def __init__(self, model="qwen3:8b", url="http://127.0.0.1:11434", timeout=90, quota_threshold=80, post=None,
                 system=SYSTEM_PROMPT):
        self.model = model
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.quota_threshold = quota_threshold
        self._post = post or self._http
        self.system = system

    @property
    def name(self):
        return f"ollama:{self.model}"

    def _http(self, body):
        req = urllib.request.Request(self.url + "/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.load(r)
        except OSError as e:
            raise BrainError("連不到 Ollama，請確認已啟動") from e

    def respond(self, event, world):
        tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                   "parameters": t["input_schema"]}} for t in TOOLS]
        messages = [{"role": "system", "content": self.system},
                    {"role": "user", "content": event_prompt(event, world, self.quota_threshold)}]
        usage = {"input_tokens": 0, "output_tokens": 0, "requests": 0}

        def ask(**extra):
            r = self._post({"model": self.model, "messages": messages, "stream": False, **extra})
            usage["requests"] += 1
            usage["input_tokens"] += r.get("prompt_eval_count") or 0
            usage["output_tokens"] += r.get("eval_count") or 0
            if r.get("error"):
                raise BrainError(f"Ollama：{r['error']}")
            return r.get("message") or {}

        for _ in range(MAX_TOOL_TURNS):
            msg = ask(tools=tools)
            calls = msg.get("tool_calls") or []
            if not calls:
                break
            messages.append(msg)
            for c in calls:
                fn = c.get("function") or {}
                messages.append({"role": "tool", "tool_name": fn.get("name"),
                                 "content": json.dumps(world.call(fn.get("name")), ensure_ascii=False)})
        else:
            raise BrainError("工具呼叫次數過多")
        try:
            line, emotion = parse_reply(msg.get("content"))
        except BrainError:
            messages.append({"role": "user", "content": "請只輸出 JSON：{\"line\": ..., \"emotion\": ...}"})
            line, emotion = parse_reply(ask(format=OUTPUT_SCHEMA).get("content"))
        return Reply(line, emotion, via=self.name, tools=list(world.called), usage=usage)


class RuleBrain:
    """Fixed sentences filled in from the same tools. No API, no cost, always available."""

    name = "rule"

    def respond(self, event, world):
        fn = getattr(self, "_" + event.name, None) or self._tap
        line, emotion = fn(event, world)
        return Reply(clean_line(line), emotion, via="rule", tools=list(world.called))

    def _print_finished(self, event, world):
        p = world.call("get_printer_status")
        name = event.detail.get("file") or p.get("file")
        who = f"{event.detail['printer']}的" if event.detail.get("printer") else ""
        return (f"{who}{name} 印好了！記得等熱床降溫再拿。" if name else f"{who}列印好了！記得等熱床降溫再拿。"), "happy"

    def _print_failed(self, event, world):
        p = world.call("get_printer_status")
        who = event.detail.get("printer") or ""
        if event.detail.get("reason") == "stopped":
            return f"{who}列印停止了，要去看一下列印機嗎？", "worried"
        pct = event.detail.get("progress") if who else p.get("progress_percent")
        return (f"{who}列印在 {pct}% 的地方出問題了，去看一下吧。" if pct else f"{who}列印好像出問題了，去看一下吧。"), "worried"

    def _quota_high(self, event, world):
        q = world.call("get_ai_quota")
        worst = None
        for t in q.get("tools", []):
            for w in t.get("windows", []):
                if not worst or w["used_percent"] > worst[1]["used_percent"]:
                    worst = (t.get("name"), w)
        if not worst:
            return "AI 額度快用完了，省著點用。", "worried"
        name, w = worst
        reset = f"，{w['resets_in']}後重置" if w.get("resets_in") else ""
        return f"{name} {w['label']}額度用了 {w['used_percent']}%{reset}。", "worried"

    def _song_change(self, event, world):
        m = world.call("get_now_playing")
        if not m.get("title"):
            return "換歌了。", "neutral"
        who = f"{m['artist']}的" if m.get("artist") else ""
        return f"換成{who}《{m['title']}》了，好聽。", "happy"

    def _long_work(self, event, world):
        work = world.scenario.get("work_minutes", world.work_minutes)
        return f"已經連續工作 {fmt_minutes(work) or '很久'}了，起來動一動吧。", "sleepy"

    def _timer_done(self, event, world):
        return "計時結束，時間到了！", "surprised"

    def _rain_soon(self, event, world):
        w = world.call("get_weather")
        hours, pct = w.get("rain_within_hours"), w.get("rain_probability_percent")
        if hours is None:
            return "等一下可能會下雨，出門記得帶傘。", "worried"
        when = "一小時內" if hours <= 1 else f"大約 {hours} 小時後"
        chance = f"（降雨機率 {pct}%）" if pct is not None else ""
        return f"{when}可能下雨{chance}，出門記得帶傘。", "worried"

    def _tap(self, event, world):
        parts = []
        p = world.call("get_printer_status")
        if p.get("stage") in ("RUNNING", "PREPARE"):
            left = f"，還要 {fmt_minutes(p['remaining_minutes'])}" if p.get("remaining_minutes") else ""
            parts.append(f"列印 {p.get('progress_percent', 0)}%{left}")
        elif p.get("failed"):
            parts.append("列印機好像出問題了")
        q = world.call("get_ai_quota")
        top = max(((t.get("name"), w) for t in q.get("tools", []) for w in t.get("windows", [])),
                  key=lambda x: x[1]["used_percent"], default=None)
        if top:
            parts.append(f"{top[0]} {top[1]['label']}額度 {top[1]['used_percent']}%")
        if not parts:
            m = world.call("get_now_playing")
            if m.get("playing"):
                parts.append(f"正在聽《{m['title']}》")
        if not parts:
            w = world.call("get_weather")
            if w.get("available"):
                rain = "，等一下可能下雨" if w.get("rain_within_hours") is not None else ""
                parts.append(f"外面{w.get('condition') or ''} {w.get('temperature_c')} 度{rain}")
        if not parts:
            return "目前一切平靜，沒什麼特別的事。", "neutral"
        worried = (p.get("failed") or top and top[1]["used_percent"] >= 80)
        return "，".join(parts) + "。", "worried" if worried else "neutral"
