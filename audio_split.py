"""
Mirrors system audio to BOTH the aux speakers and the Bluetooth speaker, in
sync -- the aux copy is deliberately delayed to match Bluetooth's own
encode/transmit/decode latency, since aux itself is otherwise instant.

Requires Windows' default playback device to be VIRTUAL_SINK_NAME (a silent
virtual device) so this script is the sole thing rendering to the two real
outputs -- toggle.pyw handles switching the default before launching this.
Started/stopped by toggle.pyw -- not meant to be run directly.
"""
import collections
import os
import sys
import threading
import traceback
from datetime import datetime

import pyaudiowpatch as pyaudio

import delay_config
import volume_util
from config import VIRTUAL_SINK_NAME, AUX_NAME, BT_NAME

CHUNK = 120  # ~2.5ms at 48kHz -- fine enough resolution for delay tuning

# This runs under pythonw.exe with no console, so anything printed to
# stdout/stderr is lost. Failures (a device name in config.py that matches
# nothing, a speaker that disconnected) would otherwise be completely
# silent -- log them somewhere the user can actually read.
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "error.log")


def log(message):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")


def find_loopback(p, name_substr):
    for d in p.get_loopback_device_info_generator():
        if name_substr.lower() in d["name"].lower():
            return d
    return None


def find_output(p, name_substr):
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        if d["maxOutputChannels"] > 0 and name_substr.lower() in d["name"].lower():
            return d
    return None


def stream_to(p, sink, out_name, delay_ms):
    dst = find_output(p, out_name)
    if dst is None:
        log(f"Output device not found: {out_name!r} -- check the name in config.py "
            f"against what list_devices.py prints.")
        return

    rate = int(sink["defaultSampleRate"])
    channels = min(int(sink["maxInputChannels"]), 2)

    in_stream = p.open(format=pyaudio.paFloat32, channels=channels, rate=rate,
                        input=True, input_device_index=sink["index"],
                        frames_per_buffer=CHUNK)
    out_stream = p.open(format=pyaudio.paFloat32, channels=channels, rate=rate,
                         output=True, output_device_index=dst["index"],
                         frames_per_buffer=CHUNK)

    chunk_ms = CHUNK / rate * 1000
    delay_chunks = max(0, round(delay_ms / chunk_ms))
    buf = collections.deque()

    try:
        # Runs until the process is killed by toggle.pyw / adjust_delay.pyw.
        while True:
            data = in_stream.read(CHUNK, exception_on_overflow=False)
            if delay_chunks == 0:
                out_stream.write(data, exception_on_underflow=False)
            else:
                buf.append(data)
                if len(buf) > delay_chunks:
                    out_stream.write(buf.popleft(), exception_on_underflow=False)
    except Exception:
        log(f"Streaming to {out_name!r} stopped:\n{traceback.format_exc()}")
    finally:
        in_stream.stop_stream(); in_stream.close()
        out_stream.stop_stream(); out_stream.close()


def main():
    # Bluetooth/aux endpoints keep whatever volume they were last left at
    # once they're no longer the Windows default device -- the taskbar
    # slider stops reaching them. Force both to 100% so neither is
    # silently capped.
    volume_util.set_volume_percent(AUX_NAME, 100)
    volume_util.set_volume_percent(BT_NAME, 100)

    p = pyaudio.PyAudio()
    try:
        sink = find_loopback(p, VIRTUAL_SINK_NAME)
        if sink is None:
            log(f"Virtual sink loopback not found: {VIRTUAL_SINK_NAME!r} -- check the "
                f"name in config.py against what list_devices.py prints.")
            sys.exit(1)

        delay_ms = delay_config.get_delay_ms()

        # Bluetooth gets the audio immediately (it adds its own latency
        # downstream); aux is held back by delay_ms to land at the same time.
        t_bt = threading.Thread(target=stream_to, args=(p, sink, BT_NAME, 0), daemon=True)
        t_aux = threading.Thread(target=stream_to, args=(p, sink, AUX_NAME, delay_ms), daemon=True)
        t_bt.start()
        t_aux.start()
        t_bt.join()
        t_aux.join()
    finally:
        p.terminate()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        log(f"Fatal error:\n{traceback.format_exc()}")
        raise
