"""
Finds the speakers available on this machine, so they can be added from the
app instead of by hand-editing config.py.

Uses the Core Audio device enumerator via pycaw rather than PortAudio.
That matters: initialising and tearing down PortAudio costs ~70ms and,
done repeatedly inside the GUI process, crashed it outright with an access
violation. This is cheap enough to call from the app's timer.

Only *active* render endpoints are listed. Windows keeps a device listed
after its cable is pulled or a Bluetooth speaker drops its audio profile,
but marks it Unplugged/NotPresent -- and a speaker in that state is the
usual reason for "it's configured but silent".
"""
import comtypes
from pycaw.constants import CLSID_MMDeviceEnumerator, DEVICE_STATE, EDataFlow
from pycaw.pycaw import AudioUtilities, IMMDeviceEnumerator

import device_store
from appconfig import VIRTUAL_SINK_NAME


def _shorten(name):
    """A tidy label from a Windows device name: 'Speakers (Realtek(R)
    Audio)' -> 'Speakers'."""
    head = name.split("(")[0].strip()
    return head or name


def all_outputs():
    """Every currently active playback endpoint, as {name, is_sink}."""
    enumerator = comtypes.CoCreateInstance(
        CLSID_MMDeviceEnumerator, IMMDeviceEnumerator,
        comtypes.CLSCTX_INPROC_SERVER)
    collection = enumerator.EnumAudioEndpoints(
        EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)

    found = []
    for i in range(collection.GetCount()):
        try:
            device = AudioUtilities.CreateDevice(collection.Item(i))
        except Exception:
            continue
        name = getattr(device, "FriendlyName", None)
        if not name:
            continue
        found.append({
            "name": name,
            "is_sink": VIRTUAL_SINK_NAME.lower() in name.lower(),
        })
    return found


def connection_status():
    """Which configured speakers are actually plugged in / connected."""
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
        available.append({"name": dev["name"], "label": _shorten(dev["name"])})
    return available
