# audio-splitter

Play the same audio out of a wired (aux) speaker and a Bluetooth speaker
**at the same time**, in sync, on Windows — no virtual audio driver to
install, no reboot, no paid software.

Windows only ever sends system audio to one output device at a time.
This routes everything through a silent virtual sink first, then fans it
out live to both a real aux output and a Bluetooth speaker, deliberately
delaying the aux copy to match Bluetooth's own encode/transmit/decode
latency so the two stay synced instead of echoing.

## Requirements

- Windows 10/11
- Python 3.10+
- A genuine **silent virtual audio device** already available on your
  machine to use as the routing point. Many Windows installs already have
  one from other software (e.g. `Speakers (SW Audio)`, installed by some
  NVIDIA driver packages as `ROOT\CSVAD`, the Microsoft sample virtual
  audio device). Check `list_devices.py`'s output for anything that looks
  virtual/software-only. If you don't have one, install a free virtual
  audio cable (e.g. VB-CABLE) and use that instead — you only need it to
  exist, not to route audio manually.

## Setup

```powershell
git clone <this repo>
cd audio-splitter
.\setup.ps1
```

`setup.ps1` creates a venv, installs Python dependencies, installs the
free `AudioDeviceCmdlets` PowerShell module (used to switch the Windows
default device and force volume), copies `config.example.py` to
`config.py`, and creates three desktop shortcuts with global hotkeys.

Then find your own device names:

```powershell
.\venv\Scripts\python.exe .\list_devices.py
```

and put them in `config.py` (gitignored, so your device names stay local):

```python
VIRTUAL_SINK_NAME = "Speakers (SW Audio)"          # your silent virtual sink
AUX_NAME = "Speakers (Realtek(R) Audio)"           # your aux-connected speakers
BT_NAME = "Headphones (Your Bluetooth Speaker)"    # your Bluetooth speaker
```

Substring matches are fine — a distinctive fragment of the name works as
well as the full string.

## Usage

| Hotkey | Action |
|---|---|
| **Ctrl+Alt+B** | Toggle the mirror on/off. On: switches Windows' default output to the virtual sink and starts mirroring to both real outputs. Off: stops the mirror and restores whatever your default device was before. |
| **Ctrl+Alt+O** | Increase the aux-side delay by 10ms (use if Bluetooth is lagging behind aux). |
| **Ctrl+Alt+P** | Decrease the aux-side delay by 10ms (use if you've overshot). |

A beep confirms each action since these run windowless (high pitch = on /
delay increased, low pitch = off; pitch scales roughly with the new delay
value on adjust).

### Calibrating the delay

Bluetooth's inherent latency (100–250ms typical, depends on codec) isn't
something software can remove — but it needs to be matched, not
eliminated, so both speakers emit sound at the same instant. Loop
something with a sharp repeated transient (a clap track, metronome, drum
loop — not sustained music) and nudge Ctrl+Alt+O/P until the two speakers
sound like one hit instead of two. The value is saved to `delay_ms.txt`
and persists across sessions.

Note: even a perfectly matched delay can still sound slightly smeared if
the two speakers sit at very different distances from your listening
position — sound itself takes about 1ms to travel every 34cm, and no
software fix can compensate for room geometry.

### Troubleshooting

**Check `error.log` first.** Everything runs windowless, so failures have
nowhere to print — a device name in `config.py` that matches nothing, or a
speaker that dropped off mid-session, gets written there instead.

- **No sound at all**: check `Get-AudioDevice -List` (after
  `Import-Module AudioDeviceCmdlets`) shows your default device as
  expected. If it's stuck on the virtual sink with nothing playing,
  something killed the mirror process without going through
  `toggle.pyw`'s cleanup — toggle it off and back on.
- **Bluetooth quieter than expected**: once a device isn't the Windows
  default, the normal volume slider stops reaching it. The mirror forces
  both outputs to 100% on every start, but check `tone_test.py` if you
  suspect it isn't taking effect.
- **Bluetooth speaker seems unreachable**: run `tone_test.py` — it sends
  a direct test tone to `BT_NAME`, bypassing the whole mirror pipeline,
  to isolate whether the problem is the Bluetooth connection itself or
  something in this project.

## How it works

`audio_split.py` opens two independent WASAPI loopback captures on the
virtual sink (one per output thread) and writes each stream out to a real
device — one immediately (Bluetooth, which adds its own latency
downstream), one through a small FIFO delay buffer (aux, to match it).
`toggle.pyw` and `adjust_delay.pyw` manage starting/stopping the worker
and switching the Windows default device, tracking the running process by
matching its command line (`proc_utils.py`) rather than a self-reported
PID file, since Python's Windows venv launcher spawns a separate stub and
child process.

## License

MIT — see [LICENSE](LICENSE).
