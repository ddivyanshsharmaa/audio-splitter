"""
Finds the speakers available on this machine, so they can be added from the
app instead of by hand-editing config.py.

Only WASAPI endpoints are offered: they are the ones the mirror can
actually drive (see find_output in audio_split.py -- the MME duplicates
Windows also exposes produce no sound on some devices). The virtual sink is
excluded because it is the routing point, not a speaker, and anything
already configured is excluded too.
"""
import pyaudiowpatch as pyaudio

import device_store
from config import VIRTUAL_SINK_NAME


def _shorten(name):
    """A tidy label from a Windows device name: 'Speakers (Realtek(R)
    Audio)' -> 'Speakers'."""
    head = name.split("(")[0].strip()
    return head or name


def all_outputs():
    """Every WASAPI playback endpoint, as {name, rate, is_sink}."""
    p = pyaudio.PyAudio()
    try:
        wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
        found = []
        for i in range(p.get_device_count()):
            d = p.get_device_info_by_index(i)
            if d["hostApi"] != wasapi or d["maxOutputChannels"] <= 0:
                continue
            found.append({
                "name": d["name"],
                "rate": int(d["defaultSampleRate"]),
                "is_sink": VIRTUAL_SINK_NAME.lower() in d["name"].lower(),
            })
        return found
    finally:
        p.terminate()


def connection_status():
    """Which configured speakers are actually plugged in / connected.

    Windows keeps listing an endpoint after the cable is pulled or a
    Bluetooth speaker drops its audio profile, but it stops being a real
    output -- worth showing, because a "silent speaker" is usually this
    rather than anything misconfigured.
    """
    live = [d["name"].lower() for d in all_outputs()]
    return {o["name"]: any(o["name"].lower() in name for name in live)
            for o in device_store.get_outputs()}


def addable_outputs():
    """Speakers that could be added: real endpoints not already configured.

    Configured names are matched as substrings, the same way the mirror
    resolves them, so a short entry still hides the full Windows device
    name it refers to.
    """
    configured = [o["name"].lower() for o in device_store.get_outputs()]
    available = []
    for dev in all_outputs():
        if dev["is_sink"]:
            continue
        lowered = dev["name"].lower()
        if any(c in lowered for c in configured):
            continue
        available.append({
            "name": dev["name"],
            "label": _shorten(dev["name"]),
            "rate": dev["rate"],
        })
    return available
