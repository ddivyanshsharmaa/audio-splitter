r"""
Interactive per-device latency tuner.

Play something with a sharp repeated beat (a clap track or metronome beats
guesswork), turn the mirror on, then run:

    .\venv\Scripts\python.exe .\calibrate.py

Pick a device with its number key, nudge with + / -, press ENTER to apply
and hear the result. Raise a device's latency if it sounds EARLY relative
to the others; lower it if it sounds LATE.
"""
import msvcrt
import os
import subprocess
import sys
import time

import latency_store
import proc_utils

HERE = os.path.dirname(os.path.abspath(__file__))
PYTHONW = os.path.join(HERE, "venv", "Scripts", "pythonw.exe")
SCRIPT = os.path.join(HERE, "audio_split.py")

STEP_MS = 10
BIG_STEP_MS = 50


def clear():
    os.system("cls")


def restart_mirror():
    was_running = proc_utils.is_running()
    if was_running:
        proc_utils.kill_all()
        time.sleep(0.5)
    subprocess.Popen([PYTHONW, SCRIPT], cwd=HERE,
                      creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
    return was_running


def draw(outputs, selected, dirty):
    clear()
    delays = latency_store.get_delays(outputs)
    slowest = max(o["latency_ms"] for o in outputs)

    print("=" * 66)
    print("  LATENCY CALIBRATION" + ("   [unapplied changes]" if dirty else ""))
    print("=" * 66)
    print()
    print(f"  {'':3} {'Device':<22} {'own latency':>12} {'held back by':>14}")
    print("  " + "-" * 62)
    for i, out in enumerate(outputs):
        marker = ">>" if i == selected else "  "
        label = out.get("label", out["name"])
        slow = "  <- slowest" if out["latency_ms"] == slowest else ""
        print(f"  {marker} {i + 1}. {label:<19} {out['latency_ms']:>8} ms "
              f"{delays[out['name']]:>11} ms{slow}")
    print()
    print("  " + "-" * 62)
    print("  1-9 select   + / -  adjust 10ms   PgUp/PgDn  adjust 50ms")
    print("  ENTER apply & restart mirror      r  reload      q  quit")
    print()
    print("  Sounds EARLY vs the others -> raise its latency (+)")
    print("  Sounds LATE  vs the others -> lower its latency (-)")
    print()
    print(f"  mirror running: {proc_utils.is_running()}")


def main():
    outputs = latency_store.get_outputs()
    if not outputs:
        sys.exit("No OUTPUTS configured in config.py.")

    selected = 0
    dirty = False
    draw(outputs, selected, dirty)

    while True:
        key = msvcrt.getch()

        # Extended keys (PgUp/PgDn/arrows) arrive as a two-byte sequence.
        if key in (b"\x00", b"\xe0"):
            ext = msvcrt.getch()
            if ext == b"I":      # PgUp
                key = b"P+"
            elif ext == b"Q":    # PgDn
                key = b"P-"
            elif ext == b"H":    # up arrow
                selected = (selected - 1) % len(outputs)
                draw(outputs, selected, dirty)
                continue
            elif ext == b"P":    # down arrow
                selected = (selected + 1) % len(outputs)
                draw(outputs, selected, dirty)
                continue
            else:
                continue

        if key in (b"q", b"Q"):
            clear()
            print("Done. Latencies saved to latencies.json.")
            if dirty:
                print("NOTE: you had unapplied changes -- press ENTER next time to apply them.")
            return

        elif key.isdigit() and key != b"0":
            idx = int(key) - 1
            if idx < len(outputs):
                selected = idx

        elif key in (b"+", b"=", b"P+"):
            step = BIG_STEP_MS if key == b"P+" else STEP_MS
            name = outputs[selected]["name"]
            new = latency_store.set_latency(name, outputs[selected]["latency_ms"] + step)
            outputs[selected]["latency_ms"] = new
            dirty = True

        elif key in (b"-", b"_", b"P-"):
            step = BIG_STEP_MS if key == b"P-" else STEP_MS
            name = outputs[selected]["name"]
            new = latency_store.set_latency(name, outputs[selected]["latency_ms"] - step)
            outputs[selected]["latency_ms"] = new
            dirty = True

        elif key in (b"\r", b"\n"):
            print("\n  applying...")
            restart_mirror()
            time.sleep(1.2)
            dirty = False

        elif key in (b"r", b"R"):
            outputs = latency_store.get_outputs()
            dirty = False

        draw(outputs, selected, dirty)


if __name__ == "__main__":
    main()
