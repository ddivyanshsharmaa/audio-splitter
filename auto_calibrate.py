r"""
Measures how much later the Bluetooth speaker actually produces sound than
a wired one, using the laptop microphone, and writes the result into the
Bluetooth latency setting.

Why a microphone: loopback capture only sees audio handed to the Bluetooth
stack. The real lag -- codec, radio, the speaker's own buffering -- happens
after that point, so it is invisible from inside the PC. A mic hears what
actually reaches the room.

Method: play a short chirp straight at ONE device at a time (bypassing the
mirror entirely), record the mic, and cross-correlate to find exactly when
it arrived. Doing it per device avoids having to tell two overlapping
clicks apart, and cross-correlation is far more robust than peak-hunting,
which is what made the first version of this pick up room noise.

The difference between the wired arrival and the Bluetooth arrival is the
Bluetooth speaker's extra latency.

Run it with the room reasonably quiet and both speakers audible:

    .\venv\Scripts\python.exe .\auto_calibrate.py
"""
import sys
import threading
import time

import numpy as np
import pyaudiowpatch as pyaudio

import device_store
import proc_utils

MIC_SUBSTR = "Microphone Array"
CHUNK = 480
RECORD_SECONDS = 3.0
PLAY_AT = 0.8            # seconds into the recording
REPEATS = 3

CHIRP_MS = 40
CHIRP_LO = 1200.0
CHIRP_HI = 6000.0


def wasapi_outputs(p):
    idx = p.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
    return [p.get_device_info_by_index(i) for i in range(p.get_device_count())
            if p.get_device_info_by_index(i)["hostApi"] == idx
            and p.get_device_info_by_index(i)["maxOutputChannels"] > 0]


def find_output(p, sub):
    for d in wasapi_outputs(p):
        if sub.lower() in d["name"].lower():
            return d
    return None


def find_mic(p):
    idx = p.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        if (d["maxInputChannels"] > 0 and d["hostApi"] == idx
                and "loopback" not in d["name"].lower()
                and MIC_SUBSTR.lower() in d["name"].lower()):
            return d
    return None


def make_chirp(rate):
    n = int(rate * CHIRP_MS / 1000)
    t = np.arange(n) / rate
    k = (CHIRP_HI - CHIRP_LO) / (CHIRP_MS / 1000)
    sig = np.sin(2 * np.pi * (CHIRP_LO * t + 0.5 * k * t * t))
    # taper the ends so the speaker doesn't add its own click
    ramp = int(n * 0.1)
    env = np.ones(n)
    env[:ramp] = np.linspace(0, 1, ramp)
    env[-ramp:] = np.linspace(1, 0, ramp)
    return (0.7 * sig * env).astype(np.float32)


def record(p, mic, out):
    rate = int(mic["defaultSampleRate"])
    ch = min(int(mic["maxInputChannels"]), 2)
    s = p.open(format=pyaudio.paFloat32, channels=ch, rate=rate, input=True,
               input_device_index=mic["index"], frames_per_buffer=CHUNK)
    frames = [s.read(CHUNK, exception_on_overflow=False)
              for _ in range(int(rate * RECORD_SECONDS / CHUNK))]
    s.stop_stream()
    s.close()
    a = np.frombuffer(b"".join(frames), dtype=np.float32)
    if ch == 2:
        a = a[::2]
    out["audio"] = a
    out["rate"] = rate


def play_to(p, dev, delay):
    time.sleep(delay)
    rate = int(dev["defaultSampleRate"])
    chirp = make_chirp(rate)
    pad = np.zeros(int(rate * 0.05), dtype=np.float32)
    sig = np.concatenate([chirp, pad])
    s = p.open(format=pyaudio.paFloat32, channels=2, rate=rate, output=True,
               output_device_index=dev["index"])
    s.write(np.repeat(sig, 2).tobytes())
    s.stop_stream()
    s.close()


def arrival_ms(recorded, rate, reference):
    """When the chirp arrived, via cross-correlation (robust to noise and
    to the two speakers having very different loudness)."""
    x = recorded - recorded.mean()
    r = reference - reference.mean()
    corr = np.correlate(x, r, mode="valid")
    if corr.size == 0:
        return None, 0.0
    peak = int(np.argmax(np.abs(corr)))
    strength = float(np.abs(corr[peak]) / (np.abs(corr).mean() + 1e-9))
    return peak / rate * 1000.0, strength


def measure_device(p, mic, dev, label):
    mic_rate = int(mic["defaultSampleRate"])
    reference = make_chirp(mic_rate)

    times = []
    for _ in range(REPEATS):
        rec = {}
        t = threading.Thread(target=record, args=(p, mic, rec))
        t.start()
        play_to(p, dev, PLAY_AT)
        t.join()

        ms, strength = arrival_ms(rec["audio"], rec["rate"], reference)
        if ms is not None and strength > 6:
            times.append(ms)
        time.sleep(0.3)

    if not times:
        print(f"  {label:<18} could not hear it")
        return None
    med = float(np.median(times))
    spread = max(times) - min(times)
    print(f"  {label:<18} arrived at {med:7.1f} ms   "
          f"(spread {spread:5.1f} ms over {len(times)} runs)")
    return med if spread < 60 else None


def main():
    outputs = [o for o in device_store.get_outputs() if o.get("enabled", True)]
    if len(outputs) < 2:
        sys.exit("Need at least two enabled outputs to compare.")

    # The laggiest configured output is the one worth measuring; the least
    # laggy is the reference. No device names are assumed.
    bt = max(outputs, key=lambda o: o["latency_ms"])
    wired = min(outputs, key=lambda o: o["latency_ms"])
    if bt is wired:
        sys.exit("All outputs have the same configured latency -- nothing to compare.")

    was_running = proc_utils.is_running()
    if was_running:
        print("Pausing the mirror so it doesn't play over the measurement...")
        proc_utils.kill_all()
        time.sleep(1.0)

    p = pyaudio.PyAudio()
    mic = find_mic(p)
    if mic is None:
        p.terminate()
        sys.exit("No microphone found.")

    bt_dev = find_output(p, bt["name"])
    wired_dev = find_output(p, wired["name"])
    if bt_dev is None or wired_dev is None:
        p.terminate()
        sys.exit("Could not find both output devices.")

    print(f"\nMeasuring with the microphone -- keep the room quiet.\n")
    wired_ms = measure_device(p, mic, wired_dev, wired.get("label", "wired"))
    bt_ms = measure_device(p, mic, bt_dev, bt.get("label", "bluetooth"))
    p.terminate()

    if wired_ms is None or bt_ms is None:
        print("\nMeasurement was not reliable enough to trust -- not changing anything.")
        print("Tune it by ear with the app's Bluetooth slider instead.")
        if was_running:
            print("Restarting the mirror.")
            import mirror_control
            mirror_control.spawn_worker()
        sys.exit(1)

    extra = bt_ms - wired_ms
    print(f"\nBluetooth is {extra:.0f} ms behind the wired speaker.")

    if extra < 0:
        print("Measured as ahead, which shouldn't happen -- not changing anything.")
    else:
        new_value = device_store.set_latency(bt["name"], int(round(extra)))
        print(f"Bluetooth latency set to {new_value} ms "
              f"(was {bt['latency_ms']} ms).")

    if was_running:
        print("Restarting the mirror.")
        import mirror_control
        mirror_control.spawn_worker()


if __name__ == "__main__":
    main()
