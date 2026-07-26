r"""
Audio Splitter control panel.

One window with a master on/off switch and, per speaker, a live latency
slider (to sync it against the others) and a volume slider. Latency and
volume both apply immediately while audio is playing -- no restart, no gap.

Run:  .\venv\Scripts\pythonw.exe .\app.pyw
"""
import tkinter as tk
from tkinter import ttk

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
        device_store.set_enabled(self.name, self.enabled.get())
        self.app.refresh_delays()
        # Adding/removing an output changes which threads must exist.
        if mirror_control.is_running():
            self.app.restart_mirror()

    def on_latency(self, _=None):
        value = int(float(self.lat_scale.get()))
        self.latency.set(value)
        device_store.set_latency(self.name, value)
        self.app.refresh_delays()

    def on_volume(self, _=None):
        value = int(float(self.vol_scale.get()))
        self.volume.set(value)
        device_store.set_volume(self.name, value)
        volume_util.set_volume_percent(self.name, value)
        self.refresh_labels()

    def refresh_labels(self):
        self.lat_value.config(text=f"{self.latency.get()} ms")
        self.vol_value.config(text=f"{self.volume.get()} %")

    def set_delay_text(self, delay_ms, is_slowest):
        if not self.enabled.get():
            self.delay_label.config(text="off", fg=MUTED)
        elif is_slowest:
            self.delay_label.config(text="slowest - others wait for it", fg=ACCENT)
        else:
            self.delay_label.config(text=f"held back {delay_ms} ms", fg=MUTED)
        self.refresh_labels()


class App:
    def __init__(self, root):
        self.root = root
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

        # --- device rows ---
        self.rows = []
        for out in device_store.get_outputs():
            self.rows.append(DeviceRow(outer, out, self))

        hint = tk.Label(
            outer, bg=BG, fg=MUTED, justify="left", anchor="w",
            font=("Segoe UI", 8),
            text=("Sounds early vs the others -> raise its latency.\n"
                  "Sounds late  vs the others -> lower its latency.\n"
                  "Changes apply live while audio is playing."),
        )
        hint.pack(fill="x", pady=(10, 0))

        self.refresh_delays()
        self.tick()

    # --- mirror control ---
    def restart_mirror(self):
        mirror_control.restart()

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
        active = [o for o in outputs if o.get("enabled", True)]
        slowest = max((o["latency_ms"] for o in active), default=None)
        by_name = {o["name"]: o for o in outputs}
        for row in self.rows:
            out = by_name.get(row.name, {})
            row.set_delay_text(
                delays.get(row.name, 0),
                out.get("latency_ms") == slowest and out.get("enabled", True),
            )

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
        self.update_status()
        self.root.after(1500, self.tick)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
