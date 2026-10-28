"""Capture BlackHole once, fan out through bounded per-speaker queues.

PortAudio (sounddevice) supplies CoreAudio streams. The existing resampler
is reused unchanged. No microphone is opened and no samples go to disk.
"""
import collections
import queue
import threading

import numpy as np

from pulse_audio import resolve
from resampler import Resampler

CHUNK = 480
QUEUE_MAX_CHUNKS = 4


def stereo_channels(frames, channels):
    if channels == 1:
        return frames.mean(axis=1, keepdims=True)
    return frames


class DelayBuffer:
    """Sink-rate delay, resized live, with silence to keep output clocks running."""
    def __init__(self):
        self.chunks = collections.deque()

    def process(self, frames, delay_chunks):
        while len(self.chunks) > delay_chunks:
            self.chunks.popleft()
        self.chunks.append(frames)
        if len(self.chunks) > delay_chunks:
            return self.chunks.popleft()
        return np.zeros_like(frames)


class MacAudio:
    def __init__(self, sink_name):
        import sounddevice as sd
        from coreaudio import CoreAudio

        self.sd = sd
        self.core = CoreAudio()
        self.sink_name = sink_name
        self.previous = None
        self.sink_id = None
        self.capture = None
        self.routes = {}
        self.delays = {}
        self.volumes = {}
        self.error = None
        self.rate = 48000

    def _devices(self):
        return [dict(d, index=i) for i, d in enumerate(self.sd.query_devices())]

    def outputs(self):
        return [{"name": d["name"], "label": d["name"],
                 "is_sink": self.sink_name.casefold() in d["name"].casefold()}
                for d in self._devices() if d["max_output_channels"] > 0]

    def start(self, outputs, delays):
        devices = self._devices()
        # Require BlackHole's capture AND playback sides; a physical mic isn't
        # a substitute for system-audio capture.
        sink = resolve([d for d in devices if d["max_input_channels"] >= 2
                        and d["max_output_channels"] >= 2], self.sink_name)
        if "blackhole" not in sink["name"].casefold():
            raise RuntimeError("macOS requires BlackHole 2ch as VIRTUAL_SINK_NAME.")
        self.sink_id = self.core.device_named(sink["name"])
        self.previous = self.core.default_output()
        if self.previous == self.sink_id:
            self.previous = None
            raise RuntimeError("Select a real output in Sound Settings before starting.")
        self.rate = int(sink["default_samplerate"])
        self.delays = dict(delays)
        for out in outputs:
            dev = resolve([d for d in devices if d["max_output_channels"] > 0], out["name"])
            if dev["index"] == sink["index"]:
                raise RuntimeError("BlackHole cannot also be a speaker (feedback).")
            if any(r["device"] == dev["index"] for r in self.routes.values()):
                raise RuntimeError("Two configured names resolve to the same speaker.")
            channels = min(2, int(dev["max_output_channels"]))
            rate = int(dev["default_samplerate"])
            stream = self.sd.OutputStream(device=dev["index"], samplerate=rate,
                                           channels=channels, dtype="float32")
            # Register before starting so even a partial start is cleaned up.
            route = {"device": dev["index"], "stream": stream,
                     "queue": queue.Queue(QUEUE_MAX_CHUNKS),
                     "stop": threading.Event(), "thread": None}
            self.routes[out["name"]] = route
            self.volumes[out["name"]] = out.get("volume", 100) / 100
            stream.start()
            thread = threading.Thread(target=self._writer,
                                      args=(out["name"], route, rate, channels), daemon=True)
            route["thread"] = thread
            thread.start()
        self.capture = self.sd.InputStream(device=sink["index"], samplerate=self.rate,
                                            channels=2, dtype="float32", blocksize=CHUNK,
                                            callback=self._capture)
        self.capture.start()
        self.core.set_default_output(self.sink_id)

    def _capture(self, frames, count, timing, status):
        for route in self.routes.values():
            try:
                route["queue"].put_nowait(frames.copy())
            except queue.Full:
                try:
                    route["queue"].get_nowait()
                    route["queue"].put_nowait(frames.copy())
                except (queue.Empty, queue.Full):
                    pass

    def _writer(self, name, route, rate, channels):
        convert = Resampler(self.rate, rate, channels)
        delay = DelayBuffer()
        try:
            while not route["stop"].is_set():
                try:
                    frames = route["queue"].get(timeout=0.1)
                except queue.Empty:
                    continue
                chunks = max(0, round(self.delays.get(name, 0) * self.rate / (1000 * CHUNK)))
                frames = delay.process(frames, chunks)
                frames = stereo_channels(frames, channels)
                data = convert.process(frames)
                if len(data):
                    route["stream"].write(data * self.volumes.get(name, 1.0))
        except Exception as exc:
            self.error = RuntimeError(f"Speaker {name!r} stopped: {exc}")

    def sync(self, outputs, delays):
        if self.error:
            raise self.error
        if self.capture is not None and not self.capture.active:
            raise RuntimeError("BlackHole capture stopped. Reconnect and restart.")
        # Speaker additions/enables and mode changes are restarted by the GUI.
        # Edits from another window/CLI are handled too, without stale threads.
        if {o["name"] for o in outputs} != set(self.routes):
            raise RuntimeError("Active speaker list changed; restart the mirror.")
        self.delays = dict(delays)
        self.volumes = {o["name"]: max(0, min(100, o.get("volume", 100))) / 100
                        for o in outputs}

    def stop(self):
        errors = []
        if self.previous is not None:
            try:
                # Restore after partial starts too (e.g. a failed default switch).
                self.core.set_default_output(self.previous)
            except Exception as exc:
                errors.append(str(exc))
            self.previous = None
        if self.capture is not None:
            try:
                self.capture.abort()
                self.capture.close()
            except Exception as exc:
                errors.append(str(exc))
            self.capture = None
        for route in self.routes.values():
            route["stop"].set()
            try:
                route["stream"].abort()
                if route["thread"]:
                    route["thread"].join(timeout=2)
                route["stream"].close()
            except Exception as exc:
                errors.append(str(exc))
        self.routes.clear()
        if errors:
            raise RuntimeError("CoreAudio cleanup: " + "; ".join(errors))
