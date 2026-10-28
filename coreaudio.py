"""The small CoreAudio surface needed to switch/restore macOS output.

No PyObjC or privileged helper: these are the public AudioObject APIs.
Only normal output is changed; the separate system-alert output is left alone.
"""
import ctypes as ct
import ctypes.util


def fourcc(value):
    return int.from_bytes(value.encode("ascii"), "big")


class Address(ct.Structure):
    _fields_ = [("selector", ct.c_uint32), ("scope", ct.c_uint32),
                ("element", ct.c_uint32)]


class CoreAudio:
    SYSTEM = 1

    def __init__(self):
        self.audio = ct.CDLL(ctypes.util.find_library("CoreAudio"))
        self.cf = ct.CDLL(ctypes.util.find_library("CoreFoundation"))
        args = [ct.c_uint32, ct.POINTER(Address), ct.c_uint32, ct.c_void_p]
        for name, tail in (
            ("AudioObjectGetPropertyDataSize", [ct.POINTER(ct.c_uint32)]),
            ("AudioObjectGetPropertyData", [ct.POINTER(ct.c_uint32), ct.c_void_p]),
            ("AudioObjectSetPropertyData", [ct.c_uint32, ct.c_void_p]),
        ):
            function = getattr(self.audio, name)
            function.argtypes = args + tail
            function.restype = ct.c_int32
        self.cf.CFStringGetCString.argtypes = [ct.c_void_p, ct.c_void_p,
                                              ct.c_long, ct.c_uint32]
        self.cf.CFStringGetCString.restype = ct.c_bool
        self.cf.CFRelease.argtypes = [ct.c_void_p]
        self.cf.CFRelease.restype = None

    @staticmethod
    def _check(status):
        if status:
            raise RuntimeError(f"CoreAudio returned OSStatus {status}")

    def _get(self, device, selector, value):
        address = Address(fourcc(selector), fourcc("glob"), 0)
        size = ct.c_uint32(ct.sizeof(value))
        self._check(self.audio.AudioObjectGetPropertyData(
            device, ct.byref(address), 0, None, ct.byref(size), ct.byref(value)))
        return value

    def default_output(self):
        return self._get(self.SYSTEM, "dOut", ct.c_uint32()).value

    def set_default_output(self, device):
        address = Address(fourcc("dOut"), fourcc("glob"), 0)
        value = ct.c_uint32(device)
        self._check(self.audio.AudioObjectSetPropertyData(
            self.SYSTEM, ct.byref(address), 0, None, ct.sizeof(value), ct.byref(value)))

    def device_named(self, name):
        address = Address(fourcc("dev#"), fourcc("glob"), 0)
        size = ct.c_uint32()
        self._check(self.audio.AudioObjectGetPropertyDataSize(
            self.SYSTEM, ct.byref(address), 0, None, ct.byref(size)))
        devices = (ct.c_uint32 * (size.value // 4))()
        self._get(self.SYSTEM, "dev#", devices)
        matches = []
        for device in devices:
            ref = self._get(device, "lnam", ct.c_void_p())
            try:
                if not ref.value:
                    continue
                buf = ct.create_string_buffer(4096)
                if self.cf.CFStringGetCString(ref, buf, len(buf), 0x08000100):
                    if buf.value.decode("utf-8") == name:
                        matches.append(device)
            finally:
                if ref.value:
                    self.cf.CFRelease(ref)
        if len(matches) != 1:
            raise RuntimeError(f"Need exactly one CoreAudio device named {name!r}")
        return matches[0]
