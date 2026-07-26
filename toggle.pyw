"""
Toggle target for the desktop shortcut / hotkey.
First press:  saves current default playback device, switches Windows'
              default output to the silent virtual sink, starts
              audio_split.py hidden in the background (beep = ON).
Second press: stops the mirror, restores the previous default device
              (beep = OFF).
"""
import os
import subprocess
import winsound

import audio_split
import proc_utils

HERE = os.path.dirname(os.path.abspath(__file__))
PREV_DEFAULT_FILE = os.path.join(HERE, "prev_default.txt")
PYTHONW = os.path.join(HERE, "venv", "Scripts", "pythonw.exe")
SCRIPT = os.path.join(HERE, "audio_split.py")

BEEP_ON = (1200, 150)
BEEP_OFF = (400, 150)


def ps(cmd: str) -> str:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return result.stdout.strip()


def get_default_playback_name() -> str:
    return ps(
        "Import-Module AudioDeviceCmdlets; "
        "(Get-AudioDevice -List | Where-Object {$_.Type -eq 'Playback' -and $_.Default -eq $true}).Name"
    )


def set_default_playback(name: str):
    safe = name.replace("'", "''")
    ps(
        "Import-Module AudioDeviceCmdlets; "
        f"$d = Get-AudioDevice -List | Where-Object {{$_.Type -eq 'Playback' -and $_.Name -eq '{safe}'}}; "
        "Set-AudioDevice -Index $d.Index"
    )


def stop():
    proc_utils.kill_all()

    if os.path.exists(PREV_DEFAULT_FILE):
        with open(PREV_DEFAULT_FILE, encoding="utf-8") as f:
            prev = f.read().strip()
        if prev:
            set_default_playback(prev)
        os.remove(PREV_DEFAULT_FILE)

    winsound.Beep(*BEEP_OFF)


def start():
    prev = get_default_playback_name()
    with open(PREV_DEFAULT_FILE, "w", encoding="utf-8") as f:
        f.write(prev)

    set_default_playback(audio_split.VIRTUAL_SINK_NAME)

    subprocess.Popen(
        [PYTHONW, SCRIPT],
        cwd=HERE,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
    )
    winsound.Beep(*BEEP_ON)


def main():
    if proc_utils.is_running():
        stop()
    else:
        start()


if __name__ == "__main__":
    main()
