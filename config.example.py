"""
Copy this file to `config.py` and edit the three names to match YOUR OWN
devices. `config.py` is gitignored, so your personal device names never end
up in version control.

Run `list_devices.py` to print the exact Windows device names it can see,
then copy the ones you want here. Substring matches are fine -- a distinctive
fragment like "SoundCore" works as well as the full device name.

VIRTUAL_SINK_NAME must be a device that produces NO real sound (a genuine
virtual/software device) -- everything is routed through it before being
split to your two real outputs, so pointing it at a real speaker will not
work. See README.md for how to find one.
"""

VIRTUAL_SINK_NAME = "Speakers (SW Audio)"          # silent virtual sink apps render to
AUX_NAME = "Speakers (Realtek(R) Audio)"           # your aux-connected speakers
BT_NAME = "Headphones (Your Bluetooth Speaker)"    # your Bluetooth speaker
