"""Offline macOS/Linux launcher. Windows keeps its existing entry points."""
import argparse
from datetime import datetime
from pathlib import Path
import runpy
import signal
import sys
import threading
import traceback

HERE = Path(__file__).resolve().parent


def log(message):
    with (HERE / "error.log").open("a", encoding="utf-8") as stream:
        stream.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")


def worker():
    import fcntl
    from unix_control import STATE, active_settings, backend, write_state

    stopping = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_: stopping.set())
    with (HERE / "unix-worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("A splitter worker already owns this repository.") from None
        audio = None
        try:
            write_state(False)
            outputs, delays = active_settings()
            if not outputs:
                raise RuntimeError("No active speakers. Add/enable one in the control panel.")
            audio = backend()
            audio.start(outputs, delays)
            names = {o["name"] for o in outputs}
            write_state(True)
            while not stopping.wait(0.3):
                outputs, delays = active_settings()
                if not outputs:
                    break
                if {o["name"] for o in outputs} != names:
                    # Also handles edits made by a second control panel.
                    audio.stop()
                    audio = backend()
                    audio.start(outputs, delays)
                    names = {o["name"] for o in outputs}
                else:
                    audio.sync(outputs, delays)
        finally:
            try:
                try:
                    write_state(False)
                finally:
                    if audio is not None:
                        audio.stop()
            finally:
                STATE.unlink(missing_ok=True)


def gui():
    import tkinter as tk
    from tkinter import messagebox

    panel = runpy.run_path(str(HERE / "app.pyw"))
    root = tk.Tk()

    def failed(kind, error, tb):
        log("".join(traceback.format_exception(kind, error, tb)))
        messagebox.showerror("Audio Splitter", str(error))

    root.report_callback_exception = failed
    panel["App"](root)
    root.mainloop()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="gui",
                        choices=("gui", "list", "check", "click", "start", "stop",
                                 "toggle", "mode", "status"))
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if sys.platform != "darwin" and not sys.platform.startswith("linux"):
        parser.error("On Windows use setup.ps1, app.pyw, and list_devices.py.")
    if args.worker:
        worker()
        return
    from unix_control import backend, mirror_control
    if args.command == "gui":
        gui()
    elif args.command in ("check", "click"):
        import unix_tones
        getattr(unix_tones, args.command)()
    elif args.command == "list":
        for device in backend().outputs():
            suffix = " [routing point]" if device["is_sink"] else ""
            print(f"{device['name']}\n  {device['label']}{suffix}")
    elif args.command == "status":
        print("ON" if mirror_control.is_running() else "OFF")
    elif args.command == "start":
        mirror_control.start()
    elif args.command == "stop":
        mirror_control.stop()
    elif args.command == "toggle":
        if mirror_control.is_running():
            mirror_control.stop()
        else:
            mirror_control.start()
        print("ON" if mirror_control.is_running() else "OFF")
    elif args.command == "mode":
        import device_store
        mode = (device_store.VIDEO_MODE if device_store.get_mode() == device_store.MUSIC_MODE
                else device_store.MUSIC_MODE)
        running = mirror_control.is_running()
        device_store.set_mode(mode)
        if running:
            mirror_control.restart()
        print(mode)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(traceback.format_exc())
        print(f"Audio Splitter: {exc}", file=sys.stderr)
        sys.exit(1)
