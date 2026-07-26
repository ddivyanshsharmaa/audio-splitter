"""Set/read playback volume for any specific audio endpoint by name, using
the real Windows Core Audio API (IAudioEndpointVolume) via pycaw -- unlike
AudioDeviceCmdlets, this works regardless of which device is default."""
from ctypes import cast, POINTER

from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume


def _find_endpoint_volume(name_substr):
    for dev in AudioUtilities.GetAllDevices():
        if dev.FriendlyName and name_substr.lower() in dev.FriendlyName.lower():
            interface = dev._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return cast(interface, POINTER(IAudioEndpointVolume))
    return None


def set_volume_percent(name_substr, percent):
    vol = _find_endpoint_volume(name_substr)
    if vol is None:
        return False
    vol.SetMasterVolumeLevelScalar(percent / 100.0, None)
    return True


def get_volume_percent(name_substr):
    vol = _find_endpoint_volume(name_substr)
    if vol is None:
        return None
    return round(vol.GetMasterVolumeLevelScalar() * 100)
