"""ESC/POS printer abstraction for the EPSON TM-m30 over USB."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum
from types import TracebackType

import usb.core
import usb.util

from image_loader import load_dithered

_ESC_INIT = b"\x1b\x40"
DEFAULT_PRINT_WIDTH_DOTS = 544


@dataclass
class Printable(ABC):
    @abstractmethod
    def to_bytes(self) -> bytes: ...


@dataclass
class Text(Printable):
    content: str

    def to_bytes(self) -> bytes:
        return self.content.encode("cp437", errors="replace")


@dataclass
class CutAndPrint(Printable):
    feed_dots: int = 16

    def to_bytes(self) -> bytes:
        return b"\x1d\x56\x41" + bytes([self.feed_dots])


class Justification(IntEnum):
    LEFT = 0
    CENTER = 1
    RIGHT = 2


@dataclass
class Image(Printable):
    """An image file printed at `width_dots` (filled to that width)."""

    path: str
    width_dots: int = DEFAULT_PRINT_WIDTH_DOTS
    justification: Justification = Justification.CENTER
    chunk_height: int = 128

    def to_bytes(self) -> bytes:
        raster = load_dithered(self.path, self.width_dots)
        width_bytes = self.width_dots // 8
        total_height = len(raster) // width_bytes
        out = bytearray()
        out += b"\x1b\x61" + bytes([self.justification])
        for y0 in range(0, total_height, self.chunk_height):
            h = min(self.chunk_height, total_height - y0)
            header = b"\x1d\x76\x30\x00" + bytes(
                [
                    width_bytes & 0xFF,
                    (width_bytes >> 8) & 0xFF,
                    h & 0xFF,
                    (h >> 8) & 0xFF,
                ]
            )
            start = y0 * width_bytes
            end = start + h * width_bytes
            out += header + raster[start:end]
        out += b"\x1b\x61\x00"
        return bytes(out)


class Printer:
    DEFAULT_VENDOR_ID = 0x04B8  # Seiko Epson Corp.
    DEFAULT_PRODUCT_ID = 0x0E20  # TM-m30

    def __init__(
        self,
        vendor_id: int = DEFAULT_VENDOR_ID,
        product_id: int = DEFAULT_PRODUCT_ID,
        write_timeout_ms: int = 5000,
    ) -> None:
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.write_timeout_ms = write_timeout_ms
        self._dev: usb.core.Device | None = None
        self._out_ep: usb.core.Endpoint | None = None

    def __enter__(self) -> "Printer":
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def open(self) -> None:
        dev = usb.core.find(idVendor=self.vendor_id, idProduct=self.product_id)
        if dev is None:
            raise RuntimeError(
                f"Printer {self.vendor_id:#06x}:{self.product_id:#06x} not found"
            )

        try:
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
        except (NotImplementedError, usb.core.USBError):
            pass

        dev.set_configuration()
        intf = dev.get_active_configuration()[(0, 0)]

        out_ep = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
            == usb.util.ENDPOINT_OUT,
        )
        if out_ep is None:
            raise RuntimeError("No OUT endpoint on printer interface")

        self._dev = dev
        self._out_ep = out_ep

    def close(self) -> None:
        if self._dev is not None:
            usb.util.dispose_resources(self._dev)
            self._dev = None
            self._out_ep = None

    def execute(self, items: list[Printable]) -> int:
        if self._out_ep is None:
            raise RuntimeError(
                "Printer not opened — use as a context manager or call open()"
            )
        payload = _ESC_INIT + b"".join(item.to_bytes() for item in items)
        return self._out_ep.write(payload, timeout=self.write_timeout_ms)
