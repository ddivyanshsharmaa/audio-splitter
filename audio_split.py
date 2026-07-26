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
import time
import traceback
from datetime import datetime

import numpy as np
import pyaudiowpatch as pyaudio

import device_store
import resampler
import volume_util
from config import VIRTUAL_SINK_NAME

# ~10ms at 44.1/48kHz. Smaller chunks give finer delay resolution but cost
# a fixed amount of Python work each, and with one resampling writer per
# speaker that overhead is what decides whether the pipeline keeps up at
# all. 120-frame chunks did not: the writers fell behind the capture and
# the queues below grew until playback ran most of a second late.
CHUNK = 480

# The queue is transport only -- the delay buffer lives in each writer --
# so it must stay shallow. A deep queue silently turns into latency: a
# backlog is only shed once the queue is completely full, so its depth is
# the maximum an output can drift behind real time. At 800 (~2s) the
# pipeline settled most of a second late; a handful of chunks rides out a
# scheduling hiccup without becoming audible lag.
QUEUE_MAX_CHUNKS = 4

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
    """Prefer the WASAPI endpoint for a device.

    Windows exposes the same speaker several times -- once per audio
    interface (MME, DirectSound, WASAPI). MME entries come first by index
    and also truncate names to 31 characters, so a naive first-match scan
    silently picks MME. That matters: some endpoints (HDMI, laptop
    speakers here) produce no sound at all through MME, and MME adds
    latency on top. The loopback capture is WASAPI, so the outputs should
    be too.
    """
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
    fallback = None
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        if d["maxOutputChannels"] <= 0 or name_substr.lower() not in d["name"].lower():
            continue
        if d["hostApi"] == wasapi:
            return d
        if fallback is None:
            fallback = d
    return fallback


class DelayController:
    """Holds the current per-device hold-back in chunks, refreshed from
    settings.json whenever it changes on disk. Lets the app retune sync
    live instead of forcing a restart (and an audible gap) per nudge."""

    POLL_SECONDS = 0.3

    def __init__(self, rate):
        self.chunk_ms = CHUNK / rate * 1000
        self.delay_chunks = {}
        self._mtime = None
        self.refresh(force=True)

    def refresh(self, force=False):
        try:
            mtime = os.path.getmtime(device_store.STORE_FILE)
        except OSError:
            mtime = None
        if not force and mtime == self._mtime:
            return
        self._mtime = mtime
        for name, ms in device_store.get_delays().items():
            self.delay_chunks[name] = max(0, round(ms / self.chunk_ms))

    def watch(self):
        while True:
            time.sleep(self.POLL_SECONDS)
            try:
                self.refresh()
            except Exception:
                pass  # a half-written json during a save is not fatal


def writer(p, dev, name, label, sink_rate, channels, q, controller):
    """Pulls captured audio off this output's queue and writes it to the
    device, holding it back so it lands together with the others.

    WASAPI only accepts a stream at the endpoint's own rate, so audio is
    resampled from the sink's rate to this device's rate on the way out.
    """
    device_rate = int(dev["defaultSampleRate"])
    try:
        out_stream = p.open(format=pyaudio.paFloat32, channels=channels,
                             rate=device_rate, output=True,
                             output_device_index=dev["index"],
                             frames_per_buffer=CHUNK)
    except Exception:
        log(f"Could not open output {label!r} ({dev['name']!r}) at {device_rate} Hz:\n"
            f"{traceback.format_exc()}")
        return

    convert = resampler.Resampler(sink_rate, device_rate, channels)
    buf = collections.deque()

    def emit(raw):
        frames = np.frombuffer(raw, dtype=np.float32).reshape(-1, channels)
        converted = convert.process(frames)
        if converted.shape[0]:
            out_stream.write(converted.tobytes(), exception_on_underflow=False)

    try:
        while True:
            data = q.get()
            if data is None:  # shutdown signal
                break

            # Delay is tracked in captured (sink-rate) chunks, so the
            # figure stays the same regardless of this device's rate.
            delay_chunks = controller.delay_chunks.get(name, 0)

            # Latency was lowered while running -- drop the excess rather
            # than replay it at speed, which would sound like a stutter.
            while len(buf) > delay_chunks:
                buf.popleft()

            if delay_chunks == 0:
                emit(data)
            else:
                buf.append(data)
                if len(buf) > delay_chunks:
                    emit(buf.popleft())
    except Exception:
        log(f"Output {label!r} stopped:\n{traceback.format_exc()}")
    finally:
        try:
            out_stream.stop_stream()
            out_stream.close()
        except Exception:
            pass


def main():
    outputs = device_store.get_outputs()
    if not outputs:
        log("No OUTPUTS configured in config.py -- nothing to do.")
        sys.exit(1)

    p = pyaudio.PyAudio()
    try:
        sink = find_loopback(p, VIRTUAL_SINK_NAME)
        if sink is None:
            log(f"Virtual sink loopback not found: {VIRTUAL_SINK_NAME!r} -- check the "
                f"name in config.py against what list_devices.py prints.")
            sys.exit(1)

        rate = int(sink["defaultSampleRate"])
        channels = min(int(sink["maxInputChannels"]), 2)

        controller = DelayController(rate)
        threading.Thread(target=controller.watch, daemon=True).start()

        # One queue per output, fed by a single capture. Capturing once and
        # fanning out guarantees every speaker gets byte-identical audio and
        # avoids opening N simultaneous loopback captures on one endpoint.
        queues = []
        threads = []
        for out in outputs:
            if not out.get("active", out.get("enabled", True)):
                continue

            dev = find_output(p, out["name"])
            if dev is None:
                log(f"Output device not found: {out['name']!r} ({out.get('label', '')}) "
                    f"-- check the name in config.py against list_devices.py output.")
                continue

            # Endpoints keep whatever volume they were last left at once
            # they're no longer the Windows default -- the taskbar slider
            # stops reaching them. Apply this device's saved level so it
            # isn't silently capped at wherever it happened to be.
            volume_util.set_volume_percent(out["name"], out.get("volume", 100))

            q = queue.Queue(maxsize=QUEUE_MAX_CHUNKS)
            t = threading.Thread(
                target=writer,
                args=(p, dev, out["name"], out.get("label", out["name"]),
                      rate, channels, q, controller),
                daemon=True,
            )
            queues.append(q)
            threads.append(t)

        if not threads:
            log("No enabled OUTPUTS matched a real device -- nothing to play to.")
            sys.exit(1)

        for t in threads:
            t.start()

        in_stream = p.open(format=pyaudio.paFloat32, channels=channels, rate=rate,
                            input=True, input_device_index=sink["index"],
                            frames_per_buffer=CHUNK)
        try:
            # Runs until the process is killed by toggle.pyw / the app.
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
