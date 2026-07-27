r"""
Audio Splitter control panel.

One window with a master on/off switch and, per speaker, a live latency
slider (to sync it against the others) and a volume slider. Latency and
volume both apply immediately while audio is playing -- no restart, no gap.

Run:  .\venv\Scripts\pythonw.exe .\app.pyw
"""
import os
import tkinter as tk
from tkinter import messagebox, ttk

import device_scan
import device_store
import mirror_control
import volume_util

BG = "#1e1f26"
FG = "#e8e8ec"
MUTED = "#8b8d98"
ACCENT = "#4a9eff"
CARD = "#282a35"
GREEN = "#3ecf8e"
RED = "#ff5f56"


class DeviceRow:
    def __init__(self, parent, output, app):
        self.app = app
        self.name = output["name"]
        self.output = output

        card = tk.Frame(parent, bg=CARD, padx=14, pady=10)
        card.pack(fill="x", pady=4)
        self.card = card

        header = tk.Frame(card, bg=CARD)
        header.pack(fill="x")

        self.enabled = tk.BooleanVar(value=output.get("enabled", True))
        chk = tk.Checkbutton(
            header, variable=self.enabled, command=self.on_enabled,
            bg=CARD, fg=FG, selectcolor=BG, activebackground=CARD,
            activeforeground=FG, highlightthickness=0, bd=0,
        )
        chk.pack(side="left")

        tk.Label(header, text=output.get("label", self.name), bg=CARD, fg=FG,
                  font=("Segoe UI", 11, "bold")).pack(side="left", padx=(4, 0))

        self.conn_label = tk.Label(header, text="", bg=CARD, fg=MUTED,
                                    font=("Segoe UI", 8))
        self.conn_label.pack(side="left", padx=(8, 0))

        tk.Button(header, text="×", command=self.on_remove, bd=0,
                   bg=CARD, fg=MUTED, activebackground=CARD, activeforeground=RED,
                   font=("Segoe UI", 12, "bold"), cursor="hand2",
                   ).pack(side="right", padx=(8, 0))

        self.delay_label = tk.Label(header, text="", bg=CARD, fg=MUTED,
                                     font=("Segoe UI", 9))
        self.delay_label.pack(side="right")

        # --- latency ---
        lat_row = tk.Frame(card, bg=CARD)
        lat_row.pack(fill="x", pady=(8, 0))
        tk.Label(lat_row, text="Latency", bg=CARD, fg=MUTED, width=8,
                  anchor="w", font=("Segoe UI", 9)).pack(side="left")

        self.latency = tk.IntVar(value=output.get("latency_ms", 0))
        self.lat_scale = ttk.Scale(
            lat_row, from_=0, to=device_store.MAX_LATENCY_MS,
            variable=self.latency, command=self.on_latency,
        )
        self.lat_scale.pack(side="left", fill="x", expand=True, padx=6)

        self.lat_value = tk.Label(lat_row, text="", bg=CARD, fg=FG, width=7,
                                   anchor="e", font=("Consolas", 9))
        self.lat_value.pack(side="right")

        # --- volume ---
        vol_row = tk.Frame(card, bg=CARD)
        vol_row.pack(fill="x", pady=(4, 0))
        tk.Label(vol_row, text="Volume", bg=CARD, fg=MUTED, width=8,
                  anchor="w", font=("Segoe UI", 9)).pack(side="left")

        self.volume = tk.IntVar(value=output.get("volume", 100))
        self.vol_scale = ttk.Scale(
            vol_row, from_=0, to=100, variable=self.volume, command=self.on_volume,
        )
        self.vol_scale.pack(side="left", fill="x", expand=True, padx=6)

        self.vol_value = tk.Label(vol_row, text="", bg=CARD, fg=FG, width=7,
                                   anchor="e", font=("Consolas", 9))
        self.vol_value.pack(side="right")

        self.refresh_labels()

    def on_enabled(self):
        if self.app.loading:
            return
        device_store.set_enabled(self.name, self.enabled.get())
        self.app.refresh_delays()
        # Adding/removing an output changes which threads must exist.
        if mirror_control.is_running():
            self.app.restart_mirror()

    def on_latency(self, _=None):
        if self.app.loading:
            return
        value = int(float(self.lat_scale.get()))
        self.latency.set(value)
        device_store.set_latency(self.name, value)
        self.app.refresh_delays()

    def on_volume(self, _=None):
        if self.app.loading:
            return
        value = int(float(self.vol_scale.get()))
        self.volume.set(value)
        device_store.set_volume(self.name, value)
        # Driving the endpoint is a COM call; at one per pixel of drag it
        # makes the slider feel sticky, so coalesce to the latest value.
        self.app.queue_volume(self.name, value)
        self.refresh_labels()

    def on_remove(self):
        if not messagebox.askyesno(
                "Remove speaker",
                f"Stop playing to {self.output.get('label', self.name)}?\n\n"
                f"Its latency and volume settings will be forgotten. You can "
                f"add it again later."):
            return
        device_store.remove_output(self.name)
        self.app.rebuild_rows()

    def set_connected(self, connected):
        if connected:
            self.conn_label.config(text="")
        else:
            self.conn_label.config(text="not connected", fg=RED)

    def load_from(self, out):
        """Adopt values changed elsewhere (tuner, hotkey, another window)."""
        self.lat_scale.set(out["latency_ms"])
        self.latency.set(out["latency_ms"])
        self.vol_scale.set(out["volume"])
        self.volume.set(out["volume"])
        self.enabled.set(out.get("enabled", True))
        self.refresh_labels()

    def refresh_labels(self):
        self.lat_value.config(text=f"{self.latency.get()} ms")
        self.vol_value.config(text=f"{self.volume.get()} %")

    def set_delay_text(self, delay_ms, is_slowest, muted_by_mode=False):
        if not self.enabled.get():
            self.delay_label.config(text="off", fg=MUTED)
        elif muted_by_mode:
            self.delay_label.config(text="sitting out in video mode", fg=RED)
        elif is_slowest:
            self.delay_label.config(text="slowest - others wait for it", fg=ACCENT)
        elif delay_ms == 0:
            self.delay_label.config(text="no delay", fg=MUTED)
        else:
            self.delay_label.config(text=f"held back {delay_ms} ms", fg=MUTED)
        self.refresh_labels()


class App:
    def __init__(self, root):
        self.root = root
        # Set while adopting values from disk, so writing them into the
        # widgets doesn't look like the user dragging and get written
        # straight back out.
        self.loading = False
        self._store_mtime = None
        self._pending_volume = {}
        self._volume_job = None
        # Scanning for devices costs ~70ms because it initialises PortAudio,
        # so it must never sit in a slider's callback path. Cached here and
        # refreshed on a slow timer instead.
        self._connected = {}
        self._conn_ticks = 0

        root.title("Audio Splitter")
        root.configure(bg=BG)
        root.resizable(False, False)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TScale", background=CARD, troughcolor=BG,
                         bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT)

        outer = tk.Frame(root, bg=BG, padx=16, pady=14)
        outer.pack(fill="both", expand=True)

        # --- header / master switch ---
        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x", pady=(0, 12))

        tk.Label(head, text="Audio Splitter", bg=BG, fg=FG,
                  font=("Segoe UI", 15, "bold")).pack(side="left")

        self.toggle_btn = tk.Button(
            head, text="", command=self.toggle, width=10, bd=0,
            font=("Segoe UI", 10, "bold"), cursor="hand2",
            activeforeground="#ffffff",
        )
        self.toggle_btn.pack(side="right")

        self.status = tk.Label(outer, text="", bg=BG, fg=MUTED,
                                font=("Segoe UI", 9), anchor="w")
        self.status.pack(fill="x", pady=(0, 8))

        # --- music / video mode ---
        mode_row = tk.Frame(outer, bg=BG)
        mode_row.pack(fill="x", pady=(0, 10))

        self.mode_buttons = {}
        for mode, text in ((device_store.MUSIC_MODE, "Music"),
                            (device_store.VIDEO_MODE, "Video")):
            b = tk.Button(mode_row, text=text, bd=0, width=11, cursor="hand2",
                           font=("Segoe UI", 9, "bold"),
                           command=lambda m=mode: self.set_mode(m))
            b.pack(side="left", padx=(0, 6))
            self.mode_buttons[mode] = b

        self.mode_note = tk.Label(mode_row, text="", bg=BG, fg=MUTED,
                                   font=("Segoe UI", 8), anchor="w", justify="left")
        self.mode_note.pack(side="left", padx=(6, 0))

        # --- device rows (rebuilt when speakers are added or removed) ---
        self.rows_container = tk.Frame(outer, bg=BG)
        self.rows_container.pack(fill="x")
        self.rows = []

        self.add_btn = tk.Button(
            outer, text="+  Add a speaker", command=self.add_speaker, bd=0,
            bg=CARD, fg=FG, activebackground=CARD, activeforeground=ACCENT,
            font=("Segoe UI", 9, "bold"), cursor="hand2", pady=7,
        )
        self.add_btn.pack(fill="x", pady=(8, 0))

        hint = tk.Label(
            outer, bg=BG, fg=MUTED, justify="left", anchor="w",
            font=("Segoe UI", 8),
            text=("A speaker sounds LATE  -> RAISE its slider (it waits less).\n"
                  "A speaker sounds EARLY -> LOWER its slider (it waits more).\n"
                  "The slider is how far that speaker lags on its own, so the\n"
                  "higher it is, the less this app holds it back.\n"
                  "Changes apply live while audio is playing."),
        )
        hint.pack(fill="x", pady=(10, 0))

        self.refresh_connections()
        self.build_rows()
        self.tick()

    # --- speaker list ---
    def build_rows(self):
        for row in self.rows:
            row.card.destroy()
        self.rows = [DeviceRow(self.rows_container, out, self)
                     for out in device_store.get_outputs()]
        self.refresh_delays()

    def rebuild_rows(self):
        """After adding or removing a speaker: redraw, and reload the worker
        since which outputs exist decides which threads it needs."""
        self._store_mtime = None      # force the next sync to re-read
        self.build_rows()
        if mirror_control.is_running():
            self.restart_mirror()

    def add_speaker(self):
        try:
            available = device_scan.addable_outputs()
        except Exception as exc:
            messagebox.showerror("Add a speaker", f"Could not scan for speakers:\n{exc}")
            return

        if not available:
            messagebox.showinfo(
                "Add a speaker",
                "No other speakers found.\n\n"
                "Everything currently connected is already in the list. Plug in "
                "or connect a speaker and try again -- Windows only offers a "
                "device once it is actually connected.")
            return

        win = tk.Toplevel(self.root)
        win.title("Add a speaker")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text="Detected speakers", bg=BG, fg=FG,
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(win, text="Pick one to start playing to it as well.",
                  bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=16)

        def choose(dev):
            device_store.add_output(dev["name"], dev["label"])
            win.destroy()
            self.rebuild_rows()

        for dev in available:
            b = tk.Button(
                win, text=f"{dev['label']}\n{dev['name']}",
                justify="left", anchor="w", bd=0, cursor="hand2",
                bg=CARD, fg=FG, activebackground=CARD, activeforeground=ACCENT,
                font=("Segoe UI", 9), padx=12, pady=8,
                command=lambda d=dev: choose(d),
            )
            b.pack(fill="x", padx=16, pady=4)

        tk.Button(win, text="Cancel", command=win.destroy, bd=0, cursor="hand2",
                   bg=BG, fg=MUTED, activebackground=BG,
                   font=("Segoe UI", 9)).pack(pady=(6, 14))

    # --- mirror control ---
    def restart_mirror(self):
        mirror_control.restart()

    def set_mode(self, mode):
        if device_store.get_mode() == mode:
            return
        device_store.set_mode(mode)
        self.refresh_delays()
        # Mode changes which speakers play at all, so the worker's threads
        # have to be rebuilt -- unlike a latency tweak, this can't be
        # picked up live.
        if mirror_control.is_running():
            self.restart_mirror()

    def refresh_mode(self):
        mode = device_store.get_mode()
        for m, b in self.mode_buttons.items():
            if m == mode:
                b.config(bg=ACCENT, fg="#0d1a2b", activebackground=ACCENT)
            else:
                b.config(bg=CARD, fg=MUTED, activebackground=CARD)
        if mode == device_store.VIDEO_MODE:
            self.mode_note.config(
                text="No delay, so audio stays with the picture.\n"
                     f"Speakers lagging over {device_store.VIDEO_MAX_LATENCY_MS} ms sit out.")
        else:
            self.mode_note.config(
                text="Every speaker in sync.\nAdds delay, so video will look out of sync.")

    def toggle(self):
        if mirror_control.is_running():
            mirror_control.stop()
        else:
            mirror_control.start()
        self.root.after(600, self.update_status)

    # --- display ---
    def refresh_delays(self):
        outputs = device_store.get_outputs()
        delays = device_store.get_delays(outputs)
        active = [o for o in outputs if o.get("active", True)]
        slowest = max((o["latency_ms"] for o in active), default=None)
        by_name = {o["name"]: o for o in outputs}

        for row in self.rows:
            out = by_name.get(row.name, {})
            row.set_delay_text(
                delays.get(row.name, 0),
                out.get("active") and out.get("latency_ms") == slowest,
                out.get("muted_by_mode", False),
            )
            row.set_connected(self._connected.get(row.name, True))
        self.refresh_mode()

    def refresh_connections(self):
        """Rescan which speakers are plugged in. Deliberately separate from
        refresh_delays, which runs on every slider movement."""
        try:
            self._connected = device_scan.connection_status()
        except Exception:
            return
        for row in self.rows:
            row.set_connected(self._connected.get(row.name, True))

    def queue_volume(self, name, value):
        self._pending_volume[name] = value
        if self._volume_job is None:
            self._volume_job = self.root.after(60, self._flush_volume)

    def _flush_volume(self):
        self._volume_job = None
        pending, self._pending_volume = self._pending_volume, {}
        for name, value in pending.items():
            volume_util.set_volume_percent(name, value)

    def sync_from_store(self):
        """Adopt changes made outside this window -- the tuner, the mode
        hotkey, a second copy of the app. Without this the sliders drift
        out of date and the next drag silently reverts whatever changed."""
        try:
            mtime = os.path.getmtime(device_store.STORE_FILE)
        except OSError:
            return
        if mtime == self._store_mtime:
            return
        self._store_mtime = mtime

        outputs = device_store.get_outputs()
        # The speaker list itself changed elsewhere -- redraw rather than
        # trying to map values onto rows that no longer line up.
        if {o["name"] for o in outputs} != {r.name for r in self.rows}:
            self.build_rows()
            return

        by_name = {o["name"]: o for o in outputs}
        self.loading = True
        try:
            for row in self.rows:
                out = by_name.get(row.name)
                if out:
                    row.load_from(out)
        finally:
            self.loading = False
        self.refresh_delays()

    def update_status(self):
        running = mirror_control.is_running()
        if running:
            self.toggle_btn.config(text="ON", bg=GREEN, activebackground=GREEN,
                                    fg="#10221a")
            self.status.config(text="Playing through every enabled speaker.")
        else:
            self.toggle_btn.config(text="OFF", bg=CARD, activebackground=CARD,
                                    fg=RED)
            self.status.config(text="Off - audio goes to your normal device.")

    def tick(self):
        self.sync_from_store()
        self.update_status()
        # Device scanning is expensive, so do it rarely -- speakers get
        # plugged in on human timescales, not every frame.
        if self._conn_ticks % 6 == 0:
            self.refresh_connections()
        self._conn_ticks += 1
        self.root.after(700, self.tick)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
