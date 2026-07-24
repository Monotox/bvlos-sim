"""Flight log ingestion and trace normalization adapters."""

from bvlos_sim.adapters.flight_log.dataflash import (
    ARDUPILOT_DATAFLASH_TEXT_FORMAT,
    FlightLogIngestionError,
    ingest_dataflash_log,
)
from bvlos_sim.adapters.flight_log.dataflash_binary import (
    ARDUPILOT_DATAFLASH_BINARY_FORMAT,
    ingest_dataflash_binary,
)
from bvlos_sim.adapters.flight_log.dispatch import (
    DEFAULT_MAX_FLIGHT_LOG_BYTES,
    MAX_FLIGHT_LOG_BYTES,
    ingest_flight_log,
)
from bvlos_sim.adapters.flight_log.io import (
    load_flight_trace,
    read_flight_trace,
    write_flight_trace,
)
from bvlos_sim.adapters.flight_log.ulog import PX4_ULOG_FORMAT, ingest_ulog

__all__ = [
    "ARDUPILOT_DATAFLASH_TEXT_FORMAT",
    "ARDUPILOT_DATAFLASH_BINARY_FORMAT",
    "DEFAULT_MAX_FLIGHT_LOG_BYTES",
    "FlightLogIngestionError",
    "MAX_FLIGHT_LOG_BYTES",
    "PX4_ULOG_FORMAT",
    "ingest_dataflash_binary",
    "ingest_dataflash_log",
    "ingest_flight_log",
    "ingest_ulog",
    "load_flight_trace",
    "read_flight_trace",
    "write_flight_trace",
]
