"""
Per-output sample rate conversion.

WASAPI in shared mode only accepts a stream at the endpoint's own mix
rate, so a 44100 Hz virtual sink cannot feed a 48000 Hz speaker directly.
Each output therefore gets its own resampler.

Linear interpolation is enough here: the ratios involved are small
(44100 <-> 48000) and the alternative is a heavyweight DSP dependency for
something that is already lossy by the time it reaches a Bluetooth codec.
Phase is carried across chunk boundaries, which is what actually matters --
resampling each chunk independently would click at every boundary.
"""
import numpy as np


class Resampler:
    def __init__(self, rate_in, rate_out, channels):
        self.rate_in = rate_in
        self.rate_out = rate_out
        self.channels = channels
        self.passthrough = rate_in == rate_out
        self.step = rate_in / rate_out   # input frames consumed per output frame
        self.prev = None                 # last input frame, for interpolating across the seam
        self.frac = 0.0                  # sub-sample position carried between chunks

    def process(self, frames):
        """frames: float32 array shaped (n, channels) -> resampled (m, channels)."""
        if self.passthrough:
            return frames

        if self.prev is not None:
            frames = np.concatenate((self.prev, frames), axis=0)

        n = frames.shape[0]
        if n < 2:
            if n:
                self.prev = frames[-1:]
            return np.zeros((0, self.channels), dtype=np.float32)

        # Output positions, in input-sample coordinates, up to the last
        # pair we can interpolate between.
        count = int(np.ceil((n - 1 - self.frac) / self.step))
        if count <= 0:
            self.prev = frames[-1:]
            return np.zeros((0, self.channels), dtype=np.float32)

        pos = self.frac + np.arange(count, dtype=np.float64) * self.step
        pos = pos[pos < n - 1]
        if pos.size == 0:
            self.prev = frames[-1:]
            return np.zeros((0, self.channels), dtype=np.float32)

        idx = pos.astype(np.int64)
        weight = (pos - idx).astype(np.float32)[:, None]
        out = frames[idx] * (1.0 - weight) + frames[idx + 1] * weight

        # Where the next chunk should resume, measured from its first frame
        # (which is the frame we are about to stash as `prev`).
        consumed = self.frac + pos.size * self.step
        self.frac = consumed - (n - 1)
        self.prev = frames[-1:]

        return out.astype(np.float32)
