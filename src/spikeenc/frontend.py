"""Front end stub — SPEC.md section 3, proposal equations (4)-(10)."""
import numpy as np


class Filterbank:
    def __init__(self, n_channels, f_min=50.0, f_max=8000.0, sample_rate=16000,
                 spacing="erb", order=4):
        self.n_channels, self.f_min, self.f_max = n_channels, f_min, f_max
        self.sample_rate, self.spacing, self.order = sample_rate, spacing, order

    @property
    def centre_frequencies(self):
        raise NotImplementedError("equation (6); endpoints exact, ascending")

    @property
    def bandwidths(self):
        raise NotImplementedError("1.019 * ERB(f_c), equation (5)")

    def impulse_response(self, channel, n_samples):
        raise NotImplementedError("equation (4)")

    def subbands(self, audio):
        raise NotImplementedError("equation (7)")

    def envelope(self, audio, method="hilbert"):
        raise NotImplementedError("equations (8)-(9)")

    def compress(self, env, method="log", epsilon=1e-8, exponent=0.3):
        raise NotImplementedError("equation (10)")
