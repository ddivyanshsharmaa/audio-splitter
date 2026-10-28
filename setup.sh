#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
case "$(uname -s)" in
  Darwin|Linux) ;;
  *) echo 'Use setup.ps1 on Windows.' >&2; exit 1 ;;
esac
python3 -c 'import tkinter' || {
  echo 'Install Python with Tk support (python3-tk on Debian/Ubuntu), then retry.' >&2
  exit 1
}
python3 -m venv venv
venv/bin/python -m pip install -r requirements-unix.txt
if [[ ! -e config.py ]]; then
  cp config.unix.example.py config.py
fi
echo 'Ready. Run: bash launch.sh list, then bash launch.sh'
echo 'macOS needs BlackHole 2ch. Linux needs pactl and a running PulseAudio/PipeWire-Pulse session.'
