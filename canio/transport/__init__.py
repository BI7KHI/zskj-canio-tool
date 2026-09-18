"""CAN 传输方式集合。"""
from __future__ import annotations

from .base import (CanTransport, FrameCallback, LogCallback, LogLine,
                   TransportError, TransportUnavailable)
from .simulator import SimulatorTransport, VirtualModule

# -- 可选后端：缺少依赖时降级，不影响其它后端 -------------------------------- #

try:
    from .slcan import HOST_BAUDS, SlcanTransport, list_serial_ports
    HAVE_SLCAN = True
except Exception as _exc:                                    # pragma: no cover
    HAVE_SLCAN = False
    _SLCAN_ERR = str(_exc)
    SlcanTransport = None            # type: ignore
    HOST_BAUDS = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]

    def list_serial_ports():         # type: ignore
        return []

try:
    from .pcan import (PCAN_BTR0BTR1, PcanTransport, api_version,
                       enumerate_channels, pcan_error_text)
    HAVE_PCAN = PcanTransport.is_available()
    PCAN_LOAD_ERROR = ""
except Exception as _exc:                                    # pragma: no cover
    HAVE_PCAN = False
    PCAN_LOAD_ERROR = str(_exc)
    PcanTransport = None             # type: ignore
    PCAN_BTR0BTR1 = {}
    enumerate_channels = lambda: []  # type: ignore
    pcan_error_text = lambda c: f"0x{c:X}"      # type: ignore
    api_version = lambda: ""                    # type: ignore

__all__ = [
    "CanTransport", "FrameCallback", "LogCallback", "LogLine",
    "TransportError", "TransportUnavailable",
    "SlcanTransport", "list_serial_ports", "HOST_BAUDS", "HAVE_SLCAN",
    "PcanTransport", "enumerate_channels", "pcan_error_text", "api_version",
    "PCAN_BTR0BTR1", "HAVE_PCAN", "PCAN_LOAD_ERROR",
    "SimulatorTransport", "VirtualModule",
]
