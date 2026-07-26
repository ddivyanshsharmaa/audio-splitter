"""
Flips between music mode (every speaker in sync, adds delay) and video
mode (drops the laggy speakers so audio stays with the picture).
Bound to Ctrl+Alt+M.

Two rising beeps  = music mode.
Two falling beeps = video mode.
"""
import winsound

import device_store
import mirror_control


def main():
    new_mode = (device_store.VIDEO_MODE
                if device_store.get_mode() == device_store.MUSIC_MODE
                else device_store.MUSIC_MODE)
    device_store.set_mode(new_mode)

    # Mode changes which outputs run at all, so the worker must be rebuilt.
    if mirror_control.is_running():
        mirror_control.restart()

    if new_mode == device_store.MUSIC_MODE:
        winsound.Beep(700, 110)
        winsound.Beep(1100, 130)
    else:
        winsound.Beep(1100, 110)
        winsound.Beep(700, 130)


if __name__ == "__main__":
    main()
