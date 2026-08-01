"""ESC/POS printer abstraction for the EPSON TM-m30."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
from types import TracebackType
import pathlib

from .image_loader import load_dithered
from .transport import Transport

_ESC_INIT = b"\x1b\x40"
DEFAULT_PRINT_WIDTH_DOTS = 544


class Justification(IntEnum):
    LEFT = 0
    CENTER = 1
    RIGHT = 2


@dataclass
class Printable(ABC):
    justification: Justification = field(default=Justification.LEFT, kw_only=True)

    def _justification_bytes(self) -> bytes:
        return b"\x1b\x61" + bytes([self.justification])

    @abstractmethod
    def to_bytes(self) -> bytes: ...


@dataclass
class Text(Printable):
    content: str

    def to_bytes(self) -> bytes:
        return (
            self._justification_bytes()
            + self.content.encode("cp437", errors="replace")
            + b"\n"
        )


@dataclass
class CutAndPrint(Printable):
    feed_dots: int = 16

    def to_bytes(self) -> bytes:
        return b"\x1d\x56\x41" + bytes([self.feed_dots])


@dataclass
class Image(Printable):
    """An image file printed at `width_dots` (filled to that width)."""

    path: str | pathlib.Path
    width_dots: int = DEFAULT_PRINT_WIDTH_DOTS
    chunk_height: int = 128

    def to_bytes(self) -> bytes:
        raster = load_dithered(str(self.path), self.width_dots)
        width_bytes = self.width_dots // 8
        total_height = len(raster) // width_bytes
        out = bytearray(self._justification_bytes())
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
        return bytes(out)


class Printer:
    def __init__(
        self,
        transport: Transport,
        write_timeout_ms: int = 5000,
    ) -> None:
        self._transport = transport
        self.write_timeout_ms = write_timeout_ms

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
        self._transport.open()

    def close(self) -> None:
        self._transport.close()

    def execute(self, items: list[Printable]) -> int:
        payload = _ESC_INIT + b"".join(item.to_bytes() for item in items)
        return self._transport.write(payload, timeout_ms=self.write_timeout_ms)
