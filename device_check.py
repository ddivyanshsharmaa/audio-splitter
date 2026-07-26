r"""
Plays a short tone through every real output device on the system, one at a
time, then through all of them at once.

Use it to confirm which speakers actually produce audible sound in your
physical setup before (or after) listing them in config.py -- notably
whether a laptop's internal speakers still work while something is plugged
into the aux jack, since many laptops mute them via hardware jack-sensing.

Run:  .\venv\Scripts\python.exe .\device_check.py
"""
import threading
import time

import numpy as np
import pyaudiowpatch as pyaudio

try:
    from config import VIRTUAL_SINK_NAME
except ImportError:  # config.py not created yet -- test everything
    VIRTUAL_SINK_NAME = None

TONE_SECONDS = 1.5
TONE_HZ = 440


def real_outputs(p):
    """Every WASAPI output endpoint except the silent virtual sink."""
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
    devices = []
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        if d["hostApi"] != wasapi or d["maxOutputChannels"] <= 0:
            continue
        if VIRTUAL_SINK_NAME and VIRTUAL_SINK_NAME.lower() in d["name"].lower():
            continue  # routing point, not a speaker -- silent by design
        devices.append(d)
    return devices


def make_tone(rate, seconds=TONE_SECONDS, freq=TONE_HZ):
    t = np.linspace(0, seconds, int(rate * seconds), False)
    # fade in/out so it doesn't click
    env = np.minimum(1.0, np.minimum(t * 20, (seconds - t) * 20))
    tone = (0.3 * np.sin(freq * t * 2 * np.pi) * env).astype(np.float32)
    return np.repeat(tone, 2).tobytes()


def play(p, dev, seconds=TONE_SECONDS):
    rate = int(dev["defaultSampleRate"])
    try:
        stream = p.open(format=pyaudio.paFloat32, channels=2, rate=rate,
                         output=True, output_device_index=dev["index"])
    except Exception as e:
        print(f"       could not open: {e}")
        return
    stream.write(make_tone(rate, seconds))
    stream.stop_stream()
    stream.close()


def main():
    p = pyaudio.PyAudio()
    devices = real_outputs(p)

    if not devices:
        print("No output devices found.")
        p.terminate()
        return

    print("=" * 62)
    print("  ONE AT A TIME -- note which ones you actually hear")
    print("=" * 62)
    for d in devices:
        print(f"  >> {d['name']}")
        play(p, d)
        time.sleep(0.4)

    if len(devices) > 1:
        print()
        print("=" * 62)
        print("  ALL AT ONCE -- note whether any drop out")
        print("=" * 62)
        threads = [threading.Thread(target=play, args=(p, d, 3.0)) for d in devices]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    p.terminate()
    print()
    print("Put the ones you heard into OUTPUTS in config.py.")
    print("Anything silent here will be silent through the mirror too.")


if __name__ == "__main__":
    main()
