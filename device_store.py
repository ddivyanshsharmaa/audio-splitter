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

# Keeping every speaker in sync means they all wait for the slowest one,
# which puts the audio behind the picture. Video mode drops any speaker
# that lags more than this, so nothing has to be held back and lip-sync
# stays correct -- at the cost of not using those speakers.
MUSIC_MODE = "music"
VIDEO_MODE = "video"
VIDEO_MAX_LATENCY_MS = 50
_MODE_KEY = "__mode__"

# The speaker list itself is stored here once the user adds or removes one,
# so the app can manage it. config.py only seeds the first run -- editing
# source files to add a speaker would be a poor way to run this.
_OUTPUTS_KEY = "__outputs__"


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


def get_mode():
    mode = _load().get(_MODE_KEY, MUSIC_MODE)
    return mode if mode in (MUSIC_MODE, VIDEO_MODE) else MUSIC_MODE


def set_mode(mode):
    if mode not in (MUSIC_MODE, VIDEO_MODE):
        raise ValueError(mode)
    data = _load()
    data[_MODE_KEY] = mode
    _save(data)
    return mode


def _base_outputs(saved=None):
    """The configured speaker list: whatever the app has saved, otherwise
    config.py's OUTPUTS as the first-run seed."""
    saved = _load() if saved is None else saved
    stored = saved.get(_OUTPUTS_KEY)
    if isinstance(stored, list) and stored:
        return [dict(o) for o in stored if isinstance(o, dict) and o.get("name")]
    return [dict(o) for o in OUTPUTS]


def add_output(name, label=None):
    """Start playing to another speaker. Existing entries are left alone so
    re-adding one keeps its tuning."""
    name = name.strip()
    if not name:
        return _base_outputs()
    data = _load()
    outputs = _base_outputs(data)
    if any(o["name"] == name for o in outputs):
        return outputs
    outputs.append({"name": name, "label": label or name, "latency_ms": 0})
    data[_OUTPUTS_KEY] = outputs
    _save(data)
    return outputs


def remove_output(name):
    """Stop playing to a speaker and forget its settings."""
    data = _load()
    outputs = [o for o in _base_outputs(data) if o["name"] != name]
    data[_OUTPUTS_KEY] = outputs
    data.pop(name, None)
    _save(data)
    return outputs


def get_outputs():
    """The configured speakers with saved latency/volume applied.

    `enabled` is the user's own on/off choice and is never touched by mode
    switching. `active` is whether it actually plays right now, which video
    mode narrows to the low-latency speakers.
    """
    saved = _load()
    mode = get_mode()
    merged = []
    for out in _base_outputs(saved):
        entry = dict(out)
        entry.setdefault("label", out["name"])
        entry.setdefault("latency_ms", 0)
        entry["volume"] = DEFAULT_VOLUME
        entry["enabled"] = True
        for key, value in saved.get(out["name"], {}).items():
            entry[key] = value
        entry["muted_by_mode"] = (mode == VIDEO_MODE
                                   and entry["latency_ms"] > VIDEO_MAX_LATENCY_MS)
        entry["active"] = entry["enabled"] and not entry["muted_by_mode"]
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
    """Map each output name -> how long to hold it back so every playing
    device emits sound at the same instant. The slowest waits for nobody.

    Only currently-active outputs count towards "slowest": that's what
    makes video mode drop the delay to zero once Bluetooth is excluded.
    """
    outputs = outputs if outputs is not None else get_outputs()
    active = [o for o in outputs if o.get("active", o.get("enabled", True))]
    if not active:
        return {o["name"]: 0 for o in outputs}
    slowest = max(o["latency_ms"] for o in active)
    return {o["name"]: max(0, slowest - o["latency_ms"]) for o in outputs}
