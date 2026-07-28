"""
Starting/stopping the mirror and swapping the Windows default playback
device. Shared by toggle.pyw and app.pyw -- keeping one copy matters,
because these two drifting apart is exactly how the "restores to the
silent virtual sink" bug appeared.
"""
import os
import subprocess

import device_store
import proc_utils
from appconfig import VIRTUAL_SINK_NAME

HERE = os.path.dirname(os.path.abspath(__file__))
PYTHONW = os.path.join(HERE, "venv", "Scripts", "pythonw.exe")
SCRIPT = os.path.join(HERE, "audio_split.py")
PREV_DEFAULT_FILE = os.path.join(HERE, "prev_default.txt")

DETACHED = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS


def ps(cmd):
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
    ).stdout.strip()


def get_default_playback():
    return ps("Import-Module AudioDeviceCmdlets; "
              "(Get-AudioDevice -List | Where-Object {$_.Type -eq 'Playback' -and "
              "$_.Default -eq $true}).Name")


def set_default_playback(name):
    """Accepts either a full device name or the substring form used in
    config.py -- an exact-match-only lookup silently does nothing when
    handed a substring, which is worse than an error because audio then
    stays pointed at a silent device."""
    safe = name.replace("'", "''").replace("[", "`[").replace("]", "`]")
    ps("Import-Module AudioDeviceCmdlets; "
       "$all = Get-AudioDevice -List | Where-Object {$_.Type -eq 'Playback'}; "
       f"$d = $all | Where-Object {{$_.Name -eq '{safe}'}} | Select-Object -First 1; "
       f"if (-not $d) {{ $d = $all | Where-Object {{$_.Name -like '*{safe}*'}} | Select-Object -First 1 }}; "
       "if ($d) { Set-AudioDevice -Index $d.Index }")


def is_virtual_sink(name):
    return bool(name) and VIRTUAL_SINK_NAME.lower() in name.lower()


def _fallback_device():
    """Something sane to hand audio back to when we have no valid saved
    device -- the first enabled real output the user configured."""
    for out in device_store.get_outputs():
        if out.get("enabled", True):
            return out["name"]
    return None


def spawn_worker():
    subprocess.Popen([PYTHONW, SCRIPT], cwd=HERE, creationflags=DETACHED)


def start():
    prev = get_default_playback()
    # Never record the virtual sink as the device to come back to -- doing
    # so means "off" would restore you to a silent device. This happens if
    # the mirror was started while the sink was already default (a crash,
    # or a second start), so guard rather than trust the current state.
    if prev and not is_virtual_sink(prev):
        with open(PREV_DEFAULT_FILE, "w", encoding="utf-8") as f:
            f.write(prev)
    set_default_playback(VIRTUAL_SINK_NAME)
    spawn_worker()


def stop():
    proc_utils.kill_all()

    prev = None
    if os.path.exists(PREV_DEFAULT_FILE):
        with open(PREV_DEFAULT_FILE, encoding="utf-8") as f:
            prev = f.read().strip()
        os.remove(PREV_DEFAULT_FILE)

    # A saved sink (from an older buggy run) is worse than no value at all.
    if is_virtual_sink(prev):
        prev = None
    if not prev:
        prev = _fallback_device()

    if prev:
        set_default_playback(prev)


def restart():
    """Reload the worker in place, leaving the default device alone."""
    proc_utils.kill_all()
    spawn_worker()


def is_running():
    return proc_utils.is_running()
