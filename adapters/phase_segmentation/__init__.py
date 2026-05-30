"""Flight phase segmentation adapters."""

from adapters.phase_segmentation.io import load_phase_segments, write_phase_segments
from adapters.phase_segmentation.segmenter import (
    CLIMB_VERT_RATE_MPS,
    LOITER_SPEED_MPS,
    SEGMENTATION_METHOD,
    TRANSIT_SPEED_MPS,
    segment_trace,
)

__all__ = [
    "CLIMB_VERT_RATE_MPS",
    "LOITER_SPEED_MPS",
    "SEGMENTATION_METHOD",
    "TRANSIT_SPEED_MPS",
    "load_phase_segments",
    "segment_trace",
    "write_phase_segments",
]
