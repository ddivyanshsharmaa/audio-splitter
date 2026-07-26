"""
Diagnostic: sends a 2-second test tone directly to BT_NAME (from config.py),
bypassing the mirror/virtual-sink pipeline entirely. Useful for telling
apart "Bluetooth speaker itself isn't reachable" from "something in the
mirror script isn't working" when troubleshooting.
"""
import numpy as np
import pyaudiowpatch as pyaudio

from config import BT_NAME

p = pyaudio.PyAudio()
dst = None
for i in range(p.get_device_count()):
    d = p.get_device_info_by_index(i)
    if d["maxOutputChannels"] > 0 and BT_NAME.lower() in d["name"].lower():
        dst = d
        break

if dst is None:
    print(f"NOT FOUND: {BT_NAME}")
else:
    print(f"Found: {dst['name']} index={dst['index']} rate={dst['defaultSampleRate']}")
    rate = int(dst["defaultSampleRate"])
    duration = 2
    freq = 440
    t = np.linspace(0, duration, int(rate * duration), False)
    tone = (0.3 * np.sin(freq * t * 2 * np.pi)).astype(np.float32)
    stereo = np.repeat(tone, 2)

    stream = p.open(format=pyaudio.paFloat32, channels=2, rate=rate,
                     output=True, output_device_index=dst["index"])
    stream.write(stereo.tobytes())
    stream.stop_stream()
    stream.close()
    print("Tone sent.")

p.terminate()
