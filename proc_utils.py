"""
Finds/kills the audio_split.py worker by matching its command line rather
than trusting a single self-reported PID -- Python 3.14's venv launcher on
Windows spawns a stub process that then launches a separate child process
to actually run the script, so a single PID file only ever tracked the
stub and silently missed the real worker.
"""
import subprocess


def find_audio_split_pids():
    # Name filter matters: without it, the powershell.exe running THIS very
    # query also matches, since its own command line contains the literal
    # search string "audio_split.py".
    out = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         "Get-CimInstance Win32_Process | "
         "Where-Object { $_.Name -like 'python*.exe' -and $_.CommandLine -like '*audio_split.py*' } | "
         "Select-Object -ExpandProperty ProcessId"],
        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
    ).stdout
    return [int(x) for x in out.split() if x.strip().isdigit()]


def is_running() -> bool:
    return len(find_audio_split_pids()) > 0


def kill_all():
    for pid in find_audio_split_pids():
        subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
