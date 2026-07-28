"""
Copy this file to `config.py` and edit it to match YOUR OWN devices.
`config.py` is gitignored, so your personal device names never end up in
version control.

Run `list_devices.py` to print the exact Windows device names it can see,
and `device_check.py` to hear which ones actually work in your setup.

VIRTUAL_SINK_NAME must be a device that produces NO real sound (a genuine
virtual/software device) -- everything is routed through it before being
split to your real outputs, so pointing it at a real speaker will not
work. See README.md for how to find one.

OUTPUTS lists every speaker you want to play at once. Names are matched as
substrings, so a distinctive fragment is enough.

You only need to get this roughly right, and only once: after the first
run the app manages the speaker list itself (Add a speaker / the x button)
and keeps it in settings.json. VIRTUAL_SINK_NAME is the one value always
read from here.

`latency_ms` is how far THAT device naturally lags behind. Wired/analog
outputs are effectively 0. Bluetooth is the big one (100-300ms depending
on codec). HDMI is usually small but not zero. Guessing is fine -- the
app's sliders tune it live, and tune.py plays a click track to do it by
ear.

The mirror delays every output by (slowest latency - its own latency), so
they all emit sound at the same instant.
"""

VIRTUAL_SINK_NAME = "Speakers (SW Audio)"    # silent virtual sink apps render to

OUTPUTS = [
    {"name": "Speakers (Realtek",  "label": "Laptop speakers", "latency_ms": 0},
    {"name": "Headphone (Realtek", "label": "Aux speakers",    "latency_ms": 0},
    {"name": "HDMI",               "label": "HDMI monitor",    "latency_ms": 40},
    {"name": "Your BT Speaker",    "label": "Bluetooth",       "latency_ms": 200},
]
