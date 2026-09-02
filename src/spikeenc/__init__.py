"""spikeenc — candidate spike encodings for audio.

Interface contract: SPEC.md. Study design: docs/proposal_v2.md.
"""
from .spiketrain import SpikeTrain

__all__ = ["SpikeTrain"]
__version__ = "0.1.0"
