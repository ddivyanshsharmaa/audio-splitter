"""Generated test tones only; never records audio. No routing changes."""
from pathlib import Path
import subprocess
import sys
import tempfile
import wave

import numpy as np

from pulse_audio import resolve
from resampler import Resampler

RATE = 48000
HERE = Path(__file__).resolve().parent


def tone(click=False):
    seconds = 0.7 if click else 1.5
    t = np.arange(int(RATE * seconds)) / RATE
    if click:
        signal = 0.15 * np.sin(2 * np.pi * 2000 * t) * np.exp(-t * 260)
        signal[int(RATE * 0.012):] = 0
    else:
        env = np.minimum(1, np.minimum(t * 20, (seconds - t) * 20))
        signal = 0.15 * np.sin(2 * np.pi * 440 * t) * env
    return np.repeat(signal.astype(np.float32)[:, None], 2, axis=1)


def play(name, frames, repeat=False):
    if sys.platform == "darwin":
        import sounddevice as sd
        devices = [dict(d, index=i) for i, d in enumerate(sd.query_devices())
                   if d["max_output_channels"] > 0]
        dev = resolve(devices, name)
        rate = int(dev["default_samplerate"])
        channels = min(2, int(dev["max_output_channels"]))
        if channels == 1:
            frames = frames.mean(axis=1, keepdims=True)
        convert = Resampler(RATE, rate, channels)
        with sd.OutputStream(device=dev["index"], samplerate=rate,
                             channels=channels, dtype="float32") as stream:
            while True:
                stream.write(convert.process(frames))
                if not repeat:
                    return
    else:
        # Keep generated files within the checkout, even during verification.
        with tempfile.TemporaryDirectory(dir=HERE, prefix=".tone-") as directory:
            path = Path(directory) / "tone.wav"
            if repeat:
                frames = np.tile(frames, (43, 1))  # 30 s without process-launch gaps
            with wave.open(str(path), "wb") as output:
                output.setnchannels(2)
                output.setsampwidth(2)
                output.setframerate(RATE)
                output.writeframes((frames * 32767).astype("<i2").tobytes())
            while True:
                child = subprocess.Popen(["paplay", f"--device={name}", str(path)])
                try:
                    if child.wait():
                        raise RuntimeError(f"paplay could not play to {name!r}")
                finally:
                    if child.poll() is None:
                        child.terminate()
                        child.wait(timeout=5)
                if not repeat:
                    return


def check():
    from unix_control import device_scan, mirror_control
    if mirror_control.is_running():
        raise RuntimeError("Turn the mirror off before checking speakers individually.")
    devices = [d for d in device_scan.all_outputs() if not d["is_sink"]]
    if not devices:
        raise RuntimeError("No speakers found.")
    frames = tone()
    for device in devices:
        print(f"Testing: {device['label']} ({device['name']})", flush=True)
        play(device["name"], frames)
    print("Add the speakers you heard in the control panel.")


def click():
    from appconfig import VIRTUAL_SINK_NAME
    from unix_control import mirror_control
    if not mirror_control.is_running():
        raise RuntimeError("Turn the mirror on before starting the click track.")
    print("Adjust latency in the control panel; Ctrl+C stops the clicks.", flush=True)
    try:
        play(VIRTUAL_SINK_NAME, tone(click=True), repeat=True)
    except KeyboardInterrupt:
        pass
