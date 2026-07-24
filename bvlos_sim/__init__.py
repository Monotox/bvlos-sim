"""BVLOS mission validation and simulation tooling.

Everything ships under this single distribution-unique package. Publishing the
subpackages as top-level ``adapters``/``estimator``/``schemas``/``scripts``
names would collide with any other distribution using them, in both directions
and without warning, because pip does not detect file conflicts.
"""
