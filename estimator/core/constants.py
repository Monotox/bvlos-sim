"""Estimator core constants."""

DEFAULT_MAX_CRAB_ANGLE_DEG = 35.0
DEFAULT_MIN_GROUNDSPEED_MPS = 3.0
EPS_DISTANCE_M = 1e-6

# Warn when groundspeed is within 10 % above the minimum (i.e. < 1.1 × min).
GROUNDSPEED_WARNING_MARGIN = 1.1
# Warn when crab angle exceeds 90 % of the configured maximum.
CRAB_ANGLE_WARNING_MARGIN = 0.9

# Turn arcs smaller than this (degrees) are skipped as numerically negligible.
MIN_TURN_ANGLE_DEG = 1.0
