"""
Nudges the aux-side delay up or down by STEP_MS and, if the mirror is
currently running, restarts it so the change takes effect immediately.
Bound to Ctrl+Alt+O (increase) / Ctrl+Alt+P (decrease) desktop shortcuts.
Beep pitch rises with the new delay value as a rough audible gauge.
"""
import os
import subprocess
import sys
import time
import winsound

import delay_config
import proc_utils

HERE = os.path.dirname(os.path.abspath(__file__))
PYTHONW = os.path.join(HERE, "venv", "Scripts", "pythonw.exe")
SCRIPT = os.path.join(HERE, "audio_split.py")

STEP_MS = 10


def restart_if_running():
    if not proc_utils.is_running():
        return
    proc_utils.kill_all()
    time.sleep(0.5)
    subprocess.Popen([PYTHONW, SCRIPT], cwd=HERE,
                      creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)


def main():
    direction = sys.argv[1] if len(sys.argv) > 1 else "+"
    current = delay_config.get_delay_ms()
    new_value = delay_config.set_delay_ms(current + STEP_MS if direction == "+" else current - STEP_MS)

    freq = 400 + min(new_value, 500)
    winsound.Beep(freq, 120)

    restart_if_running()


if __name__ == "__main__":
    main()
