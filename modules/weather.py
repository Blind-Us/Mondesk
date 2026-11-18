"""Weather for one place: free sources, no account, no key.

Open-Meteo (https://open-meteo.com) first; when it can't be reached, MET Norway's
Locationforecast (https://api.met.no) answers instead. MET Norway has no rain probability
outside the Nordics, so there "rain soon" means measurable rain in the forecast and the card
shows no percentages. Only the chosen latitude / longitude is sent. The card shows the temperature, the condition,
today's high / low and rain chance, and the next hours; `rain_soon` (rain likely within the
next hours) feeds the event centre, so the Companion can say "bring an umbrella".

Config: {"type": "weather", "place": "台北", "latitude": 25.04, "longitude": 121.56}
The settings page finds the coordinates from a place name (/api/weather/search).
"""
import calendar
import json
import time
import urllib.parse
import urllib.request

from . import BaseModule

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
SEARCH_URL = "https://geocoding-api.open-meteo.com/v1/search"
RAIN_PROBABILITY = 60   # % at which an hour counts as "rain likely"
RAIN_HOURS = 3          # how far ahead rain_soon looks
KEEP = 3 * 3600         # keep showing the last good forecast this long when the network is down

# WMO weather codes -> (label, icon). Icons are drawn by the panel (web/app.js WEATHER_ICON).
CODES = {
    0: ("晴", "sun"), 1: ("晴時多雲", "partly"), 2: ("多雲", "partly"), 3: ("陰", "cloud"),
    45: ("霧", "fog"), 48: ("霧", "fog"),
    51: ("毛毛雨", "rain"), 53: ("毛毛雨", "rain"), 55: ("毛毛雨", "rain"), 56: ("凍雨", "rain"), 57: ("凍雨", "rain"),
    61: ("小雨", "rain"), 63: ("雨", "rain"), 65: ("大雨", "rain"), 66: ("凍雨", "rain"), 67: ("凍雨", "rain"),
    71: ("小雪", "snow"), 73: ("雪", "snow"), 75: ("大雪", "snow"), 77: ("雪", "snow"),
    80: ("陣雨", "rain"), 81: ("陣雨", "rain"), 82: ("大陣雨", "rain"), 85: ("陣雪", "snow"), 86: ("陣雪", "snow"),
    95: ("雷雨", "storm"), 96: ("雷雨", "storm"), 99: ("雷雨", "storm"),
}


def describe(code, is_day=True):
    label, icon = CODES.get(int(code) if code is not None else -1, ("—", "cloud"))
    if not is_day and icon in ("sun", "partly"):
        icon = "moon" if icon == "sun" else "partly-night"
    return label, icon


def _get(url, params, timeout=8):
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "deskmon"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _round(v):
    return None if v is None else int(round(v))


def parse(raw, place="", now=None):
    """Open-Meteo forecast JSON -> the card's data. Pure, so it can be tested offline."""
    now = now or time.time()
    cur = raw.get("current") or {}
    hourly, daily = raw.get("hourly") or {}, raw.get("daily") or {}
    is_day = bool(cur.get("is_day", 1))
    label, icon = describe(cur.get("weather_code"), is_day)
    offset = raw.get("utc_offset_seconds") or 0
    # hourly times are local wall-clock strings; compare them as "seconds since epoch, local"
    local_now = now + offset
    hours = []
    for i, stamp in enumerate(hourly.get("time") or []):
        try:
            t = calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M"))
        except (ValueError, OverflowError):
            continue
        if t + 3600 <= local_now:
            continue
        pick = lambda key: (hourly.get(key) or [None] * (i + 1))[i] if i < len(hourly.get(key) or []) else None
        code = pick("weather_code")
        hours.append({"hour": int(stamp[11:13]), "temp": _round(pick("temperature_2m")),
                      "pop": _round(pick("precipitation_probability")),
                      "icon": describe(code, 6 <= int(stamp[11:13]) < 18)[1], "ahead": max(0, int((t - local_now) // 3600) + 1)})
        if len(hours) >= 8:
            break
    soon = next(({"in_hours": h["ahead"], "probability": h["pop"]} for h in hours[:RAIN_HOURS + 1]
                 if h["pop"] is not None and h["pop"] >= RAIN_PROBABILITY and h["ahead"] <= RAIN_HOURS), None)
    first = lambda key: (daily.get(key) or [None])[0]
    return {
        "place": place, "temp": _round(cur.get("temperature_2m")), "feels": _round(cur.get("apparent_temperature")),
        "code": cur.get("weather_code"), "label": label, "icon": icon, "is_day": is_day,
        "raining": bool(cur.get("precipitation")), "high": _round(first("temperature_2m_max")),
        "low": _round(first("temperature_2m_min")), "rain_today": _round(first("precipitation_probability_max")),
        "hours": hours[:6], "rain_soon": soon, "fetched": now,
    }


# ---------------------------------------------------------------- second source: MET Norway
METNO_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
METNO_RAIN_MM = 0.3   # mm in an hour that counts as rain
METNO_SYMBOLS = (("thunder", "雷雨", "storm"), ("snow", "雪", "snow"), ("sleet", "雨夾雪", "rain"),
                 ("heavyrain", "大雨", "rain"), ("lightrain", "小雨", "rain"), ("rainshowers", "陣雨", "rain"),
                 ("rain", "雨", "rain"), ("drizzle", "毛毛雨", "rain"), ("fog", "霧", "fog"),
                 ("partlycloudy", "多雲", "partly"), ("fair", "晴時多雲", "partly"), ("cloudy", "陰", "cloud"),
                 ("clearsky", "晴", "sun"))


def describe_symbol(symbol):
    """MET Norway symbol_code ("partlycloudy_night", "lightrainshowers_day"…) -> (label, icon)."""
    symbol = str(symbol or "")
    night = symbol.endswith("_night")
    for key, label, icon in METNO_SYMBOLS:
        if key in symbol:
            if night and icon in ("sun", "partly"):
                icon = "moon" if icon == "sun" else "partly-night"
            return label, icon
    return "—", "cloud"


def parse_metno(raw, place="", now=None):
    """MET Norway Locationforecast JSON -> the same card data as parse()."""
    now = now or time.time()
    rows = []
    for entry in (raw.get("properties") or {}).get("timeseries") or []:
        try:
            t = calendar.timegm(time.strptime(entry["time"], "%Y-%m-%dT%H:%M:%SZ"))
        except (KeyError, ValueError):
            continue
        data = entry.get("data") or {}
        step = data.get("next_1_hours") or data.get("next_6_hours") or {}
        rows.append((t, (data.get("instant") or {}).get("details") or {}, (step.get("summary") or {}).get("symbol_code"),
                     (step.get("details") or {}).get("precipitation_amount"), "next_1_hours" in data))
    rows = [r for r in rows if r[0] + 3600 > now]
    if not rows:
        raise ValueError("預報裡沒有資料")
    _, cur, symbol, amount, _ = rows[0]
    label, icon = describe_symbol(symbol)
    hours = []
    for t, details, sym, mm, hourly in rows[:8]:
        if not hourly:
            break
        hours.append({"hour": time.localtime(t).tm_hour, "temp": _round(details.get("air_temperature")), "pop": None,
                      "mm": mm, "icon": describe_symbol(sym)[1], "ahead": max(0, int((t - now) // 3600) + 1)})
    soon = next(({"in_hours": h["ahead"], "probability": None} for h in hours
                 if (h["mm"] or 0) >= METNO_RAIN_MM and h["ahead"] <= RAIN_HOURS), None)
    today = time.localtime(now)[:3]
    temps = [d.get("air_temperature") for t, d, *_ in rows if time.localtime(t)[:3] == today and d.get("air_temperature") is not None]
    return {
        "place": place, "temp": _round(cur.get("air_temperature")), "feels": _round(cur.get("apparent_air_temperature")),
        "code": None, "label": label, "icon": icon, "is_day": not str(symbol or "").endswith("_night"),
        "raining": bool(amount), "high": _round(max(temps)) if temps else None, "low": _round(min(temps)) if temps else None,
        "rain_today": None, "hours": hours[:6], "rain_soon": soon, "fetched": now,
    }


def search(name, count=6):
    """Places matching a name, for the settings page: [{name, region, latitude, longitude}]."""
    name = " ".join(str(name or "").split())[:60]
    if len(name) < 1:
        return []
    raw = _get(SEARCH_URL, {"name": name, "count": count, "language": "zh", "format": "json"})
    out = []
    for r in raw.get("results") or []:
        region = "、".join(x for x in (r.get("admin1"), r.get("country")) if x)
        out.append({"name": r.get("name") or name, "region": region,
                    "latitude": round(float(r["latitude"]), 4), "longitude": round(float(r["longitude"]), 4)})
    return out


class Module(BaseModule):
    type = "weather"
    default_interval = 30     # the card is refreshed often; the network is asked every EVERY seconds
    EVERY = 600

    def start(self):
        self.last = None
        self.next = 0
        self.error = ""
        self.skip_first_until = 0   # Open-Meteo unreachable: go straight to MET Norway for a while

    def coordinates(self):
        try:
            lat, lon = float(self.spec.get("latitude")), float(self.spec.get("longitude"))
        except (TypeError, ValueError):
            return None
        return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None

    def fetch(self, lat, lon):
        return _get(FORECAST_URL, {
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 2,
            "current": "temperature_2m,apparent_temperature,weather_code,is_day,precipitation",
            "hourly": "temperature_2m,precipitation_probability,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max"})

    def fetch_metno(self, lat, lon):
        return _get(METNO_URL, {"lat": round(lat, 4), "lon": round(lon, 4)}, timeout=10)

    def forecast(self, lat, lon, now):
        """Card data from the first source that answers."""
        place = str(self.spec.get("place") or "")
        if now >= self.skip_first_until:
            try:
                return {**parse(self.fetch(lat, lon), place, now), "provider": "Open-Meteo"}
            except Exception:
                self.skip_first_until = now + 3600
        return {**parse_metno(self.fetch_metno(lat, lon), place, now), "provider": "MET Norway"}

    def poll(self):
        where = self.coordinates()
        if not where:
            return {"_status": "offline", "message": "尚未設定地點"}
        now = time.time()
        if now >= self.next:
            try:
                self.last = self.forecast(*where, now)
                self.next, self.error = now + self.EVERY, ""
            except Exception as e:
                self.next = now + 120   # network hiccup: try again soon, keep the last forecast
                self.error = f"{type(e).__name__}: {e}"[:120]
        if not self.last or now - self.last["fetched"] > KEEP:
            return {"_status": "offline", "message": "讀不到天氣資料，請確認網路", "error_detail": self.error}
        return {**self.last, "stale": now - self.last["fetched"] > 2 * self.EVERY, "error_detail": self.error,
                "_status": "ok"}
