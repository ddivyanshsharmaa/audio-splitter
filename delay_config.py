import os

HERE = os.path.dirname(os.path.abspath(__file__))
DELAY_FILE = os.path.join(HERE, "delay_ms.txt")

DEFAULT_DELAY_MS = 150  # starting guess: typical A2DP SBC/AAC latency
MIN_DELAY_MS = 0
MAX_DELAY_MS = 500


def get_delay_ms() -> int:
    try:
        with open(DELAY_FILE, encoding="utf-8") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return DEFAULT_DELAY_MS


def set_delay_ms(value: int) -> int:
    value = max(MIN_DELAY_MS, min(MAX_DELAY_MS, value))
    with open(DELAY_FILE, "w", encoding="utf-8") as f:
        f.write(str(value))
    return value
