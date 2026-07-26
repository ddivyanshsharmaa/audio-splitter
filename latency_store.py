"""
Per-device tuned latency values, persisted to latencies.json.

config.py holds the starting defaults; anything tuned with calibrate.py is
saved here and takes precedence, so re-running calibration doesn't mean
editing source files.
"""
import json
import os

from config import OUTPUTS

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_FILE = os.path.join(HERE, "latencies.json")

MIN_LATENCY_MS = 0
MAX_LATENCY_MS = 1000


def _load_overrides():
    try:
        with open(STORE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_outputs():
    """config.py's OUTPUTS with any calibrated latencies applied."""
    overrides = _load_overrides()
    merged = []
    for out in OUTPUTS:
        entry = dict(out)
        if out["name"] in overrides:
            entry["latency_ms"] = overrides[out["name"]]
        merged.append(entry)
    return merged


def set_latency(name, value):
    value = max(MIN_LATENCY_MS, min(MAX_LATENCY_MS, int(value)))
    overrides = _load_overrides()
    overrides[name] = value
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2)
    return value


def get_delays(outputs=None):
    """Map each output name -> how long to hold it back so every device
    emits sound at the same instant. The slowest device waits for nobody."""
    outputs = outputs if outputs is not None else get_outputs()
    if not outputs:
        return {}
    slowest = max(o["latency_ms"] for o in outputs)
    return {o["name"]: slowest - o["latency_ms"] for o in outputs}
