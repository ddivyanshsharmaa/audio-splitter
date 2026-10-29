# audio-splitter

Play the same audio through **every speaker you own at once**, in sync, on
Windows — laptop speakers, a wired aux pair, HDMI monitor speakers, and a
Bluetooth speaker, all together. No virtual audio driver to install, no
reboot, no paid software.

The original Windows setup below is unchanged. Separate **macOS and Linux
beta** backends now share the control panel; see the platform sections below.
macOS needs BlackHole; Linux uses its existing PulseAudio/PipeWire server.

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

`config.py` only seeds the first run. Once you add or remove a speaker in
the app, the list is kept in `settings.json` (also gitignored) and the app
manages it from then on — `VIRTUAL_SINK_NAME` is the one value that always
comes from `config.py`.

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

**Adding and removing speakers:** hit **+ Add a speaker** and the app scans
for playback devices you haven't configured yet, so you don't have to edit
`config.py` by hand. The **×** on a row removes that speaker again. Only
WASAPI endpoints are offered, since those are the ones the mirror can
actually drive, and the virtual sink is excluded because it's the routing
point rather than a speaker.

Windows only exposes a device once it is genuinely connected, so plug in or
pair a speaker before adding it. Once configured, a speaker whose cable is
pulled (or whose Bluetooth audio drops) is marked **not connected** in the
window — usually the real explanation for a speaker that has gone silent.

**Ctrl+Alt+B** toggles the mirror on/off without opening the window, with
a beep for feedback (high = on, low = off).

## Music mode vs video mode

Keeping speakers in sync means they all wait for the slowest one, so with
a Bluetooth speaker in the mix *every* speaker is delayed by its lag. For
music that's unnoticeable. For video it isn't: the audio ends up a couple
of hundred milliseconds behind the picture, and nothing here can fix that,
because the only real correction would be delaying the video — which lives
in your player or browser, not this app.

So there are two modes, switchable in the app or with **Ctrl+Alt+M**:

| Mode | What plays | Delay added |
|---|---|---|
| **Music** | every enabled speaker, all in sync | as much as the slowest speaker lags |
| **Video** | only speakers lagging under 50 ms | none — audio stays with the picture |

Video mode doesn't change your per-speaker on/off choices; it just sets
the laggy ones aside until you switch back. The threshold is
`VIDEO_MAX_LATENCY_MS` in `device_store.py`.

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

- a speaker sounds **late** relative to the others → **raise** its slider
- a speaker sounds **early** relative to the others → **lower** its slider

The slider is how far that speaker lags *on its own*, and each output is
held back by `(slowest − its own)`. So raising a speaker's number reduces
how long it waits, making it play sooner — which is the fix when it sounds
late. Lowering it makes it wait longer.

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
- **A speaker marked "not connected"**: Windows keeps listing an endpoint
  after its cable is pulled, a monitor sleeps, or a Bluetooth speaker drops
  its audio profile. Nothing here can revive it — reconnect the device.
- **Laptop speakers silent while something is in the headphone jack**: most
  laptops mute them in hardware when the jack is occupied. No software can
  override that.
- **A speaker plays noticeably later than the others even at 0ms**: some
  outputs have vendor DSP (loudness equalisation and the like) applied
  after this app, which adds its own delay. Rather than fight it, measure
  the gap and set that speaker's latency to it — compensating is what the
  slider is for.

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

Outputs are resolved to their **WASAPI** endpoint specifically. Windows
exposes each speaker once per audio interface (MME, DirectSound, WASAPI),
MME entries come first and truncate names to 31 characters, and some
endpoints — HDMI and laptop speakers among them — produce no sound at all
through MME. WASAPI in shared mode also only accepts a stream at the
endpoint's own rate, so `resampler.py` converts per output, carrying phase
across chunk boundaries so the seams don't click.

`toggle.pyw` and the app share `mirror_control.py` for starting, stopping
and swapping the Windows default device. It tracks the worker by matching
command lines (`proc_utils.py`) rather than a self-reported PID, since
Python's Windows venv launcher spawns a separate stub and child process,
and it refuses to record the virtual sink as the device to restore — doing
so would leave all audio pointed at a silent device.

`volume_util.py` drives the Core Audio `IAudioEndpointVolume` interface via
pycaw, which works regardless of which device is default, and caches it per
device. `device_scan.py` uses the same Core Audio enumerator rather than
PortAudio: initialising PortAudio costs ~70ms, and doing it repeatedly from
the GUI crashed the process outright.

## macOS (beta)

**beta: built and checked on Windows with automated tests and syntax/type
checks; not yet tested on real Mac/Linux hardware.** The checks performed
were Python compilation, bash syntax checks and automated tests, not a
static type checker. Hardware playback and permissions still need validation.

Requirements: Python 3.10+ with Tk support, and the free
[BlackHole 2ch](https://github.com/ExistentialAudio/BlackHole) virtual audio
driver. Install BlackHole following its upstream instructions, then:

```bash
git clone --branch main https://github.com/ddivyanshsharmaa/audio-splitter
cd audio-splitter
bash setup.sh
bash launch.sh list
bash launch.sh
```

If an existing `config.py` came from Windows, edit it before starting:
set `VIRTUAL_SINK_NAME = "BlackHole 2ch"` and `OUTPUTS = []`, and remove or
rename the old `settings.json` to seed a fresh speaker list. Setup preserves
existing configuration. New installations get `config.unix.example.py`,
with an empty list; use **+ Add a speaker** to choose your real outputs.

Start with a **real speaker selected in System Settings > Sound > Output**.
Turn the mirror on in the panel. It opens BlackHole's input, opens each real
speaker's output, then uses CoreAudio to select BlackHole as normal system
output. Turning it off restores the previous device. No Multi-Output Device
is needed: the worker itself plays to the speakers. Do not add BlackHole,
an aggregate containing it, or a Multi-Output Device containing it as a
speaker, because that creates a feedback path. The separate system-alert
output and applications pinned to a specific output are not redirected.

Grant **Microphone** access to the launching terminal/Python if macOS asks
(System Settings > Privacy & Security > Microphone). BlackHole capture is
an audio-input stream, although the physical microphone is never opened.
No Accessibility or Input Monitoring permission is needed. Follow macOS's
normal approval prompts when installing BlackHole; do not disable security
features. Run in your logged-in desktop session, without `sudo`.

Latency uses the existing resampler and a FIFO per speaker (roughly 10 ms
steps at 48 kHz). Volume is software gain applied only to this mirror,
within about 300 ms of a slider change. Speaker enable/add/remove and mode
changes restart routing briefly. Independent hardware clocks can still
cause occasional dropped chunks or audible drift over long sessions; this
is not a sample-locked professional audio interface. Only stereo and mono
outputs are supported. Reopen the panel/worker if a newly connected device
does not appear. Identically named devices require distinct OS names.
The mirror's volume gain cannot override a muted/quiet physical device;
check the device's own volume and OS sound settings too.

## Linux (beta)

**beta: built and checked on Windows with automated tests and syntax/type
checks; not yet tested on real Mac/Linux hardware.** The checks performed
were Python compilation, bash syntax checks and automated tests, not a
static type checker. Hardware playback and server compatibility still need
validation.

Requirements: Python 3.10+, Tk, Python venv support, and a running user
**PulseAudio or PipeWire-Pulse** audio server. Install `pactl` and `paplay`
from your distribution (typically `pulseaudio-utils`; this supplies clients,
not a reason to replace PipeWire). `pactl` must support JSON output and
`get-default-sink`. ALSA-only systems are unsupported. For example, on
Debian/Ubuntu the Python components are `python3`, `python3-venv` and
`python3-tk`.

```bash
git clone --branch main https://github.com/ddivyanshsharmaa/audio-splitter
cd audio-splitter
bash setup.sh
pactl --format=json list sinks
pactl get-default-sink
bash launch.sh list
bash launch.sh
```

Setup creates `config.py` from the Unix example with
`VIRTUAL_SINK_NAME = "audio_splitter"` and `OUTPUTS = []`. If migrating an
existing checkout, update those values and rename its Windows
`settings.json` first. Add real speakers in the panel; names are the stable
server sink identifiers, with readable descriptions displayed beside them.
Exact names win over substrings, and ambiguous matches are rejected.

The worker creates one `module-null-sink` and one `module-loopback` for each
active output. It selects the silent sink as default and moves existing
streams on the previous default into it. Streams explicitly routed to other
outputs stay there. Stop restores the old default, moves applications off
the silent sink, and unloads only the modules this worker created.

Run as the **same desktop user as your sound server**, without `sudo`.
No input-device group, microphone, or global-keyboard permission is needed:
the source is the virtual sink's monitor, never a microphone. Both X11 and
Wayland use the same audio route. The application adds no network service,
telemetry or audio recording; setup downloads Python dependencies.

Linux latency is a **server buffer target**, set to 10 ms plus the calculated
hold-back. The server may clamp it to a device's minimum, and it cannot
remove Bluetooth delay or guarantee precise synchronisation. Tune by ear.
Changing latency recreates the affected loopback, causing a brief gap;
volume updates apply to that loopback's stream within about 300 ms without
changing the speaker's global volume. Video mode omits speakers over 50 ms
and adds no synchronisation hold-back, but the server still adds buffering.
If your server lacks either module, startup fails and cleans up; there is
no ALSA or native PipeWire-only fallback.
The physical sink must also be unmuted at an audible volume. PulseAudio's
flat-volume policy, if enabled, may link stream and device levels.

## macOS/Linux commands and limits

```bash
bash launch.sh                 # shared control panel
bash launch.sh list            # available output devices
bash launch.sh check           # gentle tone per real output, mirror OFF
bash launch.sh start           # background worker, restores output on stop
bash launch.sh status          # ON/OFF (process readiness, not proof of audibility)
bash launch.sh toggle          # mirror on/off
bash launch.sh mode            # music/video; preserves enabled choices
bash launch.sh click           # metronome through mirror; Ctrl+C stops clicks
bash launch.sh stop            # stop worker and restore previous output
```

For sync calibration, start the mirror and click track, then adjust sliders
in the panel using the same late/early guidance as Windows. `check` tests
outputs sequentially; turn the mirror on to check them together. The old
Windows helpers (`list_devices.py`, `device_check.py`, `tune.py`,
`auto_calibrate.py`, `toggle*.pyw`, `setup.ps1`) remain Windows entry points.
Microphone-based automatic calibration is not ported; use the click track
and sliders. Linux `click` has a short process restart gap every 30 seconds.

Global hotkeys/desktop shortcuts are **not installed automatically** on
macOS/Linux. You can bind commands with your desktop's keyboard-shortcut
settings or macOS Shortcuts/Quick Actions: use absolute paths, for example
`bash /path/to/audio-splitter/launch.sh toggle`. Suggested bindings are
Ctrl+Alt+K (panel), Ctrl+Alt+B (toggle), Ctrl+Alt+M (mode), where available;
the OS/desktop may reserve them. There are no Windows-style feedback beeps;
the panel and CLI report state. Closing the panel leaves the worker running;
use Off or `stop` before logging out.

Read `error.log` if startup fails or a device disconnects. A failed route
stops the Unix worker and attempts to restore normal output. If the original
device disappeared, select another real speaker in OS sound settings.
Do not run simultaneous copies from different checkouts or combine this
route with another audio mirror. Normal shutdown and startup exceptions
clean up; SIGKILL, power loss, or a sound-server crash cannot run cleanup.

After forced termination on macOS, select a real output in Sound Settings.
On Linux, select a real default with `pactl set-default-sink REAL_SINK`, inspect
`pactl list short modules`, and use `pactl unload-module ID` for the
splitter's loopbacks and null sink only (loopbacks first). Match their
arguments to `source=audio_splitter.monitor` / `sink_name=audio_splitter`;
do not unload unrelated modules. Reopen/re-route any application still on
the old sink. A pre-existing sink with the configured name is deliberately
not taken over or deleted.

### Development checks

Tests run with standard Python on Windows, macOS and Linux. Tests needing
NumPy, psutil or Tk skip with an explanation when those optional test
dependencies are absent. Install the appropriate requirements file to run
all tests (Tk comes from your Python/OS installation), then run:

```bash
python -m unittest discover -s tests -v
python tests/test_cross_platform.py
bash -n setup.sh
bash -n launch.sh
```

Tests cover settings/modes, chunked resampling, live FIFO delay, mocked
Linux/Mac routing and rollback, process identity checks, and the shared
panel's platform imports. Mocked tests do not prove native audio playback.

The routing uses the public [PulseAudio modules](https://www.freedesktop.org/wiki/Software/PulseAudio/Documentation/User/Modules/),
[pactl commands](https://manpages.debian.org/testing/pulseaudio-utils/pactl.1.en.html),
[PipeWire PulseAudio modules](https://docs.pipewire.org/page_pulse_modules.html),
[sounddevice streams](https://python-sounddevice.readthedocs.io/), and
[CoreAudio AudioObject APIs](https://developer.apple.com/documentation/coreaudio/audioobjectsetpropertydata(_:_:_:_:_:_:)).

## License

MIT — see [LICENSE](LICENSE).
