# audio-splitter

Play the same audio through **every speaker you own at once**, in sync, on
Windows — laptop speakers, a wired aux pair, HDMI monitor speakers, and a
Bluetooth speaker, all together. No virtual audio driver to install, no
reboot, no paid software.

Windows only ever sends system audio to one output device at a time. This
routes everything through a silent virtual sink, captures it once, and
fans it out live to as many real outputs as you list — delaying each one
just enough to cancel out the differences in their natural latency, so
Bluetooth doesn't echo behind the wired speakers.

## Requirements

- Windows 10/11
- Python 3.10+
- A genuine **silent virtual audio device** to use as the routing point.
  Many Windows installs already have one from other software (e.g.
  `Speakers (SW Audio)`, the Microsoft sample virtual audio device that
  ships with some driver packages). Check `list_devices.py`'s output for
  anything virtual/software-only. If you don't have one, install a free
  virtual audio cable (e.g. VB-CABLE) — you only need it to exist, not to
  route anything manually.

## Setup

```powershell
git clone https://github.com/ddivyanshsharmaa/audio-splitter
cd audio-splitter
.\setup.ps1
```

`setup.ps1` creates a venv, installs dependencies, installs the free
`AudioDeviceCmdlets` PowerShell module, copies `config.example.py` to
`config.py`, and creates the desktop shortcuts with global hotkeys.

Then list your devices:

```powershell
.\venv\Scripts\python.exe .\list_devices.py
```

and list every speaker you want in `config.py` (gitignored, so your device
names stay local):

```python
VIRTUAL_SINK_NAME = "Speakers (SW Audio)"

OUTPUTS = [
    {"name": "Speakers (Realtek",  "label": "Laptop speakers", "latency_ms": 0},
    {"name": "Headphone (Realtek", "label": "Aux speakers",    "latency_ms": 0},
    {"name": "HDMI",               "label": "HDMI monitor",    "latency_ms": 40},
    {"name": "Your BT Speaker",    "label": "Bluetooth",       "latency_ms": 200},
]
```

Names are matched as substrings, so a distinctive fragment is enough.

Finally, confirm each one is actually audible in your physical setup:

```powershell
.\venv\Scripts\python.exe .\device_check.py
```

This plays a tone through each device one at a time, then all together.
Worth doing — some monitors have no speakers at all, and **many laptops
mute their internal speakers whenever something is plugged into the 3.5mm
jack** (hardware jack-sensing), which no software can override.

## Usage

Launch the control panel (**Ctrl+Alt+K**, or the *Audio Splitter* desktop
shortcut) for a window with a master on/off switch and, per speaker, a
live latency slider, a volume slider, and an enable checkbox:

```
  Audio Splitter                                    [  ON  ]
  Playing through every enabled speaker.

  [x] Laptop speakers                      held back 310 ms
      Latency  [|---------------]                     0 ms
      Volume   [=============|--]                    85 %

  [x] Bluetooth              slowest - others wait for it
      Latency  [=====|----------]                   310 ms
      Volume   [================]                   100 %
```

Latency and volume both apply **immediately while audio is playing** — no
restart, no gap — so you can tune sync by ear in real time.

**Ctrl+Alt+B** toggles the mirror on/off without opening the window, with
a beep for feedback (high = on, low = off).

## Calibrating sync

Each output declares its own latency — how far *that device* naturally
lags. The mirror then holds every output back by
`(slowest latency − its own latency)`, so they all emit sound at the same
instant. Bluetooth is usually the slowest by far (100–300ms depending on
codec); wired analog is effectively zero.

Bluetooth latency can't be removed — only *matched*, by making everything
else wait for it.

Play something with a sharp repeated beat (a clap track or metronome beats
guesswork), turn the mirror on, then drag the latency sliders:

- a speaker sounds **early** relative to the others → raise its latency
- a speaker sounds **late** relative to the others → lower its latency

Settings are saved to `settings.json` and persist across sessions.

Note: even perfectly matched delays can sound slightly smeared if your
speakers sit at very different distances from you — sound itself takes
about 1ms to travel every 34cm, and no software can fix room geometry.

### Troubleshooting

**Check `error.log` first.** Everything runs windowless, so failures have
nowhere to print — a name in `config.py` matching no device, or a speaker
that dropped off mid-session, gets written there instead.

- **No sound at all**: check your default device (`Import-Module
  AudioDeviceCmdlets; Get-AudioDevice -List`). If it's stuck on the
  virtual sink with nothing running, something killed the mirror without
  going through `toggle.pyw`'s cleanup — toggle off and on.
- **One speaker silent**: run `device_check.py` to test it in isolation,
  bypassing the mirror entirely. If it's silent there too, the problem is
  that device or its connection, not this project.
- **A speaker is quieter than expected**: once a device isn't the Windows
  default, the taskbar volume slider stops reaching it — use the app's
  per-device volume slider instead, which drives the endpoint directly.

## How it works

`audio_split.py` opens a single WASAPI loopback capture on the virtual
sink and fans each chunk out to one queue per output. A writer thread per
device drains its queue through a FIFO delay buffer sized to that device's
hold-back, then writes to the endpoint. Capturing once and distributing
guarantees every speaker gets byte-identical audio; bounded queues mean a
device that stalls drops old audio instead of drifting further behind.

Delay buffers are resized on the fly: a watcher thread notices when
`settings.json` changes and updates each writer's hold-back, which is what
makes the app's sliders take effect mid-playback rather than on restart.

`toggle.pyw` manages the Windows default device and the worker process,
tracking it by matching command lines (`proc_utils.py`) rather than a
self-reported PID, since Python's Windows venv launcher spawns a separate
stub and child process. `volume_util.py` uses the Core Audio
`IAudioEndpointVolume` interface via pycaw to set per-device volume, which
works regardless of which device is currently default.

## License

MIT — see [LICENSE](LICENSE).
