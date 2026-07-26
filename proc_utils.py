"""
Finds/kills the audio_split.py worker by matching its command line rather
than trusting a single self-reported PID -- Python's venv launcher on
Windows spawns a stub process that then launches a separate child process
to actually run the script, so a PID file only ever tracked the stub and
silently missed the real worker.

Uses psutil rather than shelling out: the app polls this about once a
second, and spawning a PowerShell process to run a WMI process query at
that rate is far more expensive than the check itself.
"""
import os

import psutil

SCRIPT_NAME = "audio_split.py"


def find_audio_split_pids():
    pids = []
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (proc.info["name"] or "").lower()
            if not name.startswith("python"):
                continue
            cmdline = proc.info["cmdline"] or []
            if any(SCRIPT_NAME in part for part in cmdline):
                pids.append(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return pids


def is_running() -> bool:
    return bool(find_audio_split_pids())


def kill_all():
    me = os.getpid()
    for pid in find_audio_split_pids():
        if pid == me:
            continue
        try:
            proc = psutil.Process(pid)
            for child in proc.children(recursive=True):
                try:
                    child.kill()
                except psutil.Error:
                    pass
            proc.kill()
        except psutil.Error:
            pass
