r"""
Speaker sync tuner.

Plays a soft click every 700ms through the mirror, so every speaker gets
it, and lets you adjust the laggiest speaker's latency without leaving the
window. Misalignment is easy to hear on a repeating click: two taps
instead of one. When it collapses to a single sharp tap, they're in sync.

A Bluetooth speaker's real lag can't be measured from the PC -- loopback
only sees audio handed to the Bluetooth stack, and laptop mic arrays tend
to cancel out speaker sound -- so this is tuned by ear.

Run with the mirror ON:

    .\venv\Scripts\python.exe .\tune.py
"""
import msvcrt
import sys
import threading
import time

import numpy as np
import pyaudiowpatch as pyaudio

import device_store
import proc_utils
from appconfig import VIRTUAL_SINK_NAME

CLICK_EVERY = 0.7
AMPLITUDE = 0.18      # deliberately soft
STEP = 10
BIG_STEP = 50

stop = threading.Event()


def find_output(p, sub):
    idx = p.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        if (d["maxOutputChannels"] > 0 and sub.lower() in d["name"].lower()
                and d["hostApi"] == idx):
            return d
    return None


def click_track(rate, seconds=CLICK_EVERY):
    n = int(rate * seconds)
    buf = np.zeros(n, dtype=np.float32)
    # short percussive blip: a few cycles of a high tone with a fast decay
    ln = int(rate * 0.012)
    t = np.arange(ln) / rate
    blip = np.sin(2 * np.pi * 2000 * t) * np.exp(-t * 260)
    buf[:ln] = (AMPLITUDE * blip).astype(np.float32)
    return np.repeat(buf, 2).tobytes()


def player():
    p = pyaudio.PyAudio()
    sink = find_output(p, VIRTUAL_SINK_NAME)
    if sink is None:
        print("Could not find the virtual sink.")
        p.terminate()
        return
    rate = int(sink["defaultSampleRate"])
    data = click_track(rate)
    s = p.open(format=pyaudio.paFloat32, channels=2, rate=rate, output=True,
               output_device_index=sink["index"])
    try:
        while not stop.is_set():
            s.write(data)
    except Exception:
        pass
    finally:
        s.stop_stream()
        s.close()
        p.terminate()


def laggiest_output():
    """The speaker everyone else is waiting for -- in practice the
    Bluetooth one, but picked by latency so no device name is assumed."""
    outputs = [o for o in device_store.get_outputs() if o.get("enabled", True)]
    if not outputs:
        return None
    return max(outputs, key=lambda o: o["latency_ms"])


def draw(label, value, volume):
    print("\033[2J\033[H", end="")   # clear
    print("=" * 58)
    print("  SPEAKER SYNC TUNER")
    print("=" * 58)
    print()
    print(f"    Tuning       :  {label}")
    print(f"    Its latency  :  {value} ms")
    print(f"    Volume (all) :  {volume} %")
    print()
    print("  Listen to the repeating click:")
    print("    two taps  ->  not in sync yet")
    print("    one tap   ->  synced")
    print()
    print(f"  {label} sounds LATE  ->  press  +   (raise)")
    print(f"  {label} sounds EARLY ->  press  -   (lower)")
    print()
    print("  + / -   10 ms        PgUp / PgDn   50 ms")
    print("  [ / ]   volume       q  quit")
    print()
    print("  Changes apply within about half a second.")


def set_all_volumes(vol):
    import volume_util
    for o in device_store.get_outputs():
        device_store.set_volume(o["name"], vol)
        volume_util.set_volume_percent(o["name"], vol)


def main():
    if not proc_utils.is_running():
        print("The mirror isn't running -- turn it on first (Ctrl+Alt+B).")
        sys.exit(1)

    target = laggiest_output()
    if target is None:
        sys.exit("No enabled outputs configured.")

    label = target.get("label", target["name"])
    value = target["latency_ms"]
    volume = target.get("volume", 30)

    t = threading.Thread(target=player, daemon=True)
    t.start()

    draw(label, value, volume)
    try:
        while True:
            key = msvcrt.getch()
            if key in (b"\x00", b"\xe0"):
                ext = msvcrt.getch()
                if ext == b"I":
                    value = device_store.set_latency(target["name"], value + BIG_STEP)
                elif ext == b"Q":
                    value = device_store.set_latency(target["name"], value - BIG_STEP)
                else:
                    continue
            elif key in (b"q", b"Q"):
                break
            elif key in (b"+", b"="):
                value = device_store.set_latency(target["name"], value + STEP)
            elif key in (b"-", b"_"):
                value = device_store.set_latency(target["name"], value - STEP)
            elif key == b"]":
                volume = min(100, volume + 5)
                set_all_volumes(volume)
            elif key == b"[":
                volume = max(0, volume - 5)
                set_all_volumes(volume)
            else:
                continue
            draw(label, value, volume)
    finally:
        stop.set()
        time.sleep(0.3)
        print(f"\n{label} latency saved at {value} ms.")


if __name__ == "__main__":
    main()
