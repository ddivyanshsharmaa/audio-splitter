"""Copy to config.py on macOS/Linux. Add speakers in the control panel.

On macOS install BlackHole 2ch first. On Linux the worker creates its own
silent sink in your existing PulseAudio or PipeWire-Pulse session.
"""
import sys

VIRTUAL_SINK_NAME = "BlackHole 2ch" if sys.platform == "darwin" else "audio_splitter"
OUTPUTS = []
