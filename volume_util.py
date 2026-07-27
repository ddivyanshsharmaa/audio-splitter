"""Set/read playback volume for any specific audio endpoint by name, using
the real Windows Core Audio API (IAudioEndpointVolume) via pycaw -- unlike
AudioDeviceCmdlets, this works regardless of which device is default.

The endpoint interface is cached per device. Re-enumerating every audio
device and activating a fresh COM object on each call is not just slow: at
the rate a dragged volume slider produces calls, that churn crashed the
app with an access violation.
"""
from ctypes import POINTER, cast

from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

_cache = {}


def _endpoint(name_substr):
    volume = _cache.get(name_substr)
    if volume is not None:
        return volume

    for dev in AudioUtilities.GetAllDevices():
        friendly = getattr(dev, "FriendlyName", None)
        if not friendly or name_substr.lower() not in friendly.lower():
            continue
        try:
            interface = dev._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        except Exception:
            continue
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        _cache[name_substr] = volume
        return volume
    return None


def _forget(name_substr):
    """Drop a cached interface -- used when a call fails, since the device
    may have been unplugged and the old interface is then dead."""
    _cache.pop(name_substr, None)


def set_volume_percent(name_substr, percent):
    volume = _endpoint(name_substr)
    if volume is None:
        return False
    try:
        volume.SetMasterVolumeLevelScalar(max(0.0, min(1.0, percent / 100.0)), None)
        return True
    except Exception:
        _forget(name_substr)
        return False


def get_volume_percent(name_substr):
    volume = _endpoint(name_substr)
    if volume is None:
        return None
    try:
        return round(volume.GetMasterVolumeLevelScalar() * 100)
    except Exception:
        _forget(name_substr)
        return None
