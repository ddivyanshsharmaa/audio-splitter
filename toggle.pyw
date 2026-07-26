"""
Toggle target for the desktop shortcut / hotkey (Ctrl+Alt+B).
First press:  switches Windows' default output to the silent virtual sink
              and starts the mirror hidden in the background, so every
              speaker in config.py's OUTPUTS plays at once (beep = ON).
Second press: stops the mirror and restores the previous default device
              (beep = OFF).
"""
import winsound

import mirror_control

BEEP_ON = (1200, 150)
BEEP_OFF = (400, 150)


def main():
    if mirror_control.is_running():
        mirror_control.stop()
        winsound.Beep(*BEEP_OFF)
    else:
        mirror_control.start()
        winsound.Beep(*BEEP_ON)


if __name__ == "__main__":
    main()
