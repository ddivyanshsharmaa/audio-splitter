"""macOS/Linux services for the shared Tk panel and command-line launcher.

The worker owns routing, restores it on SIGTERM, and holds an advisory lock.
A PID is only used after checking its creation time AND exact command line.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "unix_audio.py"
STATE = HERE / "unix-worker.json"


def backend():
    from appconfig import VIRTUAL_SINK_NAME
    if sys.platform == "darwin":
        from mac_audio import MacAudio
        return MacAudio(VIRTUAL_SINK_NAME)
    if sys.platform.startswith("linux"):
        from pulse_audio import PulseAudio
        return PulseAudio(VIRTUAL_SINK_NAME)
    raise RuntimeError("Use the existing setup.ps1 and app.pyw on Windows.")


def active_settings():
    import device_store
    outputs = [o for o in device_store.get_outputs() if o["active"]]
    delays = device_store.get_delays(outputs)
    if device_store.get_mode() == device_store.VIDEO_MODE:
        delays = {o["name"]: 0 for o in outputs}
    return outputs, delays


def _worker():
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        proc = psutil.Process(data["pid"])
        command = proc.cmdline()
        if abs(proc.create_time() - data["created"]) > 0.001:
            return None, None
        if len(command) != 3 or Path(command[1]).resolve() != SCRIPT or command[2] != "--worker":
            return None, None
        if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
            return None, None
        return proc, data
    except (OSError, ValueError, KeyError, TypeError, psutil.Error):
        return None, None


def write_state(ready):
    data = {"pid": os.getpid(), "created": psutil.Process().create_time(), "ready": ready}
    temporary = STATE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data), encoding="utf-8")
    os.replace(temporary, STATE)


class MirrorControl:
    def is_running(self):
        proc, data = _worker()
        return proc is not None and data.get("ready", False)

    def start(self):
        proc, _ = _worker()
        child = None
        if proc is None:
            with (HERE / "error.log").open("a", encoding="utf-8") as log:
                child = subprocess.Popen([sys.executable, str(SCRIPT), "--worker"],
                                         cwd=HERE, stdout=log, stderr=log,
                                         start_new_session=True)
        for _ in range(100):
            if self.is_running():
                return
            if child is not None and child.poll() is not None and _worker()[0] is None:
                break
            time.sleep(0.1)
        # Do not leave a late-starting process taking over sound after failure.
        try:
            self.stop()
        finally:
            # The child may not have published its state file yet, so stop()
            # cannot necessarily find it. The Popen handle still identifies
            # the process we launched, without trusting a stale PID file.
            if child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    raise RuntimeError("Worker did not finish cleanup; see error.log. "
                                       "Select your normal output in OS sound settings.") from None
        raise RuntimeError("Audio routing did not start. See error.log; "
                           "check devices and permissions, then retry.")

    def stop(self):
        proc, _ = _worker()
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except psutil.NoSuchProcess:
                pass
            except psutil.TimeoutExpired:
                raise RuntimeError("Worker did not finish cleanup; see error.log. "
                                   "Select your normal output in OS sound settings.") from None

    def restart(self):
        self.stop()
        self.start()


class DeviceScan:
    def all_outputs(self):
        return backend().outputs()

    def _configured_names(self, devices):
        import device_store
        from pulse_audio import resolve
        matched = {}
        for out in device_store.get_outputs():
            try:
                matched[out["name"]] = resolve(devices, out["name"])["name"]
            except RuntimeError:
                matched[out["name"]] = None
        return matched

    def connection_status(self):
        return {name: match is not None
                for name, match in self._configured_names(self.all_outputs()).items()}

    def addable_outputs(self):
        devices = self.all_outputs()
        configured = set(self._configured_names(devices).values())
        return [d for d in devices if not d["is_sink"] and d["name"] not in configured]


class VolumeControl:
    def set_volume_percent(self, name, value):
        # The panel already saved settings.json. Worker.sync applies software
        # gain on macOS, or loopback-stream gain on Linux, within 300 ms.
        return True


device_scan = DeviceScan()
mirror_control = MirrorControl()
volume_util = VolumeControl()
