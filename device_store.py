"""
Per-device settings (latency + volume), persisted to settings.json.

config.py holds the starting defaults; anything changed in the app is saved
here and takes precedence, so tuning never means editing source files.
"""
import json
import os

from config import OUTPUTS

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_FILE = os.path.join(HERE, "settings.json")

MIN_LATENCY_MS = 0
MAX_LATENCY_MS = 1000
DEFAULT_VOLUME = 100


def _load():
    try:
        with open(STORE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data):
    tmp = STORE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    # Atomic replace so a reader never sees a half-written file.
    os.replace(tmp, STORE_FILE)


def get_outputs():
    """config.py's OUTPUTS with any saved latency/volume applied."""
    saved = _load()
    merged = []
    for out in OUTPUTS:
        entry = dict(out)
        entry.setdefault("label", out["name"])
        entry.setdefault("latency_ms", 0)
        entry["volume"] = DEFAULT_VOLUME
        entry["enabled"] = True
        for key, value in saved.get(out["name"], {}).items():
            entry[key] = value
        merged.append(entry)
    return merged


def _set_field(name, field, value):
    data = _load()
    data.setdefault(name, {})[field] = value
    _save(data)
    return value


def set_latency(name, value):
    value = max(MIN_LATENCY_MS, min(MAX_LATENCY_MS, int(value)))
    return _set_field(name, "latency_ms", value)


def set_volume(name, value):
    value = max(0, min(100, int(value)))
    return _set_field(name, "volume", value)


def set_enabled(name, value):
    return _set_field(name, "enabled", bool(value))


def get_delays(outputs=None):
    """Map each output name -> how long to hold it back so every enabled
    device emits sound at the same instant. The slowest waits for nobody."""
    outputs = outputs if outputs is not None else get_outputs()
    active = [o for o in outputs if o.get("enabled", True)]
    if not active:
        return {o["name"]: 0 for o in outputs}
    slowest = max(o["latency_ms"] for o in active)
    return {o["name"]: max(0, slowest - o["latency_ms"]) for o in outputs}
