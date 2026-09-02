"""SpikeTrain — implements SPEC.md section 2 exactly.

This is a data container, not research code: it is provided complete so that
every encoder returns the same thing and canonical ordering is guaranteed
consistent. Change it only if SPEC.md changes.
"""
from dataclasses import dataclass, field
import numpy as np


@dataclass(frozen=True)
class SpikeTrain:
    channel: np.ndarray      # int32,   (N,)
    time: np.ndarray         # float64, (N,), seconds
    polarity: np.ndarray     # int8,    (N,), +1 or -1
    n_channels: int
    duration: float
    params: dict = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "channel", np.asarray(self.channel, dtype=np.int32))
        object.__setattr__(self, "time", np.asarray(self.time, dtype=np.float64))
        object.__setattr__(self, "polarity", np.asarray(self.polarity, dtype=np.int8))
        n = len(self.time)
        if len(self.channel) != n or len(self.polarity) != n:
            raise ValueError("channel, time and polarity must be the same length")

    @classmethod
    def from_events(cls, channel, time, polarity, n_channels, duration, params=None):
        """Build a train in canonical order: time ascending, then channel
        ascending, then polarity descending (+1 before -1). SPEC.md section 2."""
        channel = np.asarray(channel, dtype=np.int32)
        time = np.asarray(time, dtype=np.float64)
        polarity = np.asarray(polarity, dtype=np.int8)
        order = np.lexsort((-polarity, channel, time))
        return cls(channel[order], time[order], polarity[order],
                   int(n_channels), float(duration), dict(params or {}))

    @classmethod
    def empty(cls, n_channels, duration, params=None):
        return cls(np.empty(0, np.int32), np.empty(0, np.float64),
                   np.empty(0, np.int8), int(n_channels), float(duration),
                   dict(params or {}))

    def counts_per_channel(self) -> np.ndarray:
        return np.bincount(self.channel, minlength=self.n_channels).astype(np.int64)

    def times_in_channel(self, c: int) -> np.ndarray:
        t = self.time[self.channel == c]
        return np.sort(t)

    def __len__(self) -> int:
        return int(len(self.time))
