"""
Mirrors system audio to EVERY speaker listed in config.py at once -- laptop
speakers, aux, HDMI monitor, Bluetooth -- keeping them in sync by delaying
each output to land together with the slowest one (usually Bluetooth).

Requires Windows' default playback device to be VIRTUAL_SINK_NAME (a silent
virtual device) so this script is the sole thing rendering to the real
outputs -- toggle.pyw handles switching the default before launching this.
Started/stopped by toggle.pyw -- not meant to be run directly.
"""
import collections
import os
import queue
import sys
import threading
import traceback
from datetime import datetime

import pyaudiowpatch as pyaudio

import latency_store
import volume_util
from config import VIRTUAL_SINK_NAME

CHUNK = 120  # ~2.5ms at 48kHz -- fine enough resolution for delay tuning

# Bounded so a stalled/disconnected device can't grow its queue forever.
# 800 chunks is ~2s of audio, comfortably above the 1000ms max delay.
QUEUE_MAX_CHUNKS = 800

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


def writer(p, dev, label, delay_ms, rate, channels, q):
    """Pulls captured audio off this output's queue and writes it to the
    device, holding it back by delay_ms so it lands with the others."""
    try:
        out_stream = p.open(format=pyaudio.paFloat32, channels=channels, rate=rate,
                             output=True, output_device_index=dev["index"],
                             frames_per_buffer=CHUNK)
    except Exception:
        log(f"Could not open output {label!r} ({dev['name']!r}):\n{traceback.format_exc()}")
        return

    chunk_ms = CHUNK / rate * 1000
    delay_chunks = max(0, round(delay_ms / chunk_ms))
    buf = collections.deque()

    try:
        while True:
            data = q.get()
            if data is None:  # shutdown signal
                break
            if delay_chunks == 0:
                out_stream.write(data, exception_on_underflow=False)
            else:
                buf.append(data)
                if len(buf) > delay_chunks:
                    out_stream.write(buf.popleft(), exception_on_underflow=False)
    except Exception:
        log(f"Output {label!r} stopped:\n{traceback.format_exc()}")
    finally:
        try:
            out_stream.stop_stream()
            out_stream.close()
        except Exception:
            pass


def main():
    outputs = latency_store.get_outputs()
    if not outputs:
        log("No OUTPUTS configured in config.py -- nothing to do.")
        sys.exit(1)

    delays = latency_store.get_delays(outputs)

    # Endpoints keep whatever volume they were last left at once they're no
    # longer the Windows default device -- the taskbar slider stops reaching
    # them. Force every output to 100% so none is silently capped.
    for out in outputs:
        volume_util.set_volume_percent(out["name"], 100)

    p = pyaudio.PyAudio()
    try:
        sink = find_loopback(p, VIRTUAL_SINK_NAME)
        if sink is None:
            log(f"Virtual sink loopback not found: {VIRTUAL_SINK_NAME!r} -- check the "
                f"name in config.py against what list_devices.py prints.")
            sys.exit(1)

        rate = int(sink["defaultSampleRate"])
        channels = min(int(sink["maxInputChannels"]), 2)

        # One queue per output, fed by a single capture. Capturing once and
        # fanning out guarantees every speaker gets byte-identical audio and
        # avoids opening N simultaneous loopback captures on one endpoint.
        queues = []
        threads = []
        for out in outputs:
            dev = find_output(p, out["name"])
            if dev is None:
                log(f"Output device not found: {out['name']!r} ({out.get('label', '')}) "
                    f"-- check the name in config.py against list_devices.py output.")
                continue
            q = queue.Queue(maxsize=QUEUE_MAX_CHUNKS)
            t = threading.Thread(
                target=writer,
                args=(p, dev, out.get("label", out["name"]), delays[out["name"]],
                      rate, channels, q),
                daemon=True,
            )
            queues.append(q)
            threads.append(t)

        if not threads:
            log("None of the configured OUTPUTS matched a real device -- nothing to play to.")
            sys.exit(1)

        for t in threads:
            t.start()

        in_stream = p.open(format=pyaudio.paFloat32, channels=channels, rate=rate,
                            input=True, input_device_index=sink["index"],
                            frames_per_buffer=CHUNK)
        try:
            # Runs until the process is killed by toggle.pyw / calibrate.py.
            while True:
                data = in_stream.read(CHUNK, exception_on_overflow=False)
                for q in queues:
                    try:
                        q.put_nowait(data)
                    except queue.Full:
                        # Device fell behind -- drop the oldest chunk rather
                        # than let it drift further and further behind.
                        try:
                            q.get_nowait()
                            q.put_nowait(data)
                        except (queue.Empty, queue.Full):
                            pass
        finally:
            in_stream.stop_stream()
            in_stream.close()
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
