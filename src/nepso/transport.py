"""Transport backends for communicating with ESC/POS printers."""

import socket
from abc import ABC, abstractmethod

import usb.core
import usb.util


class Transport(ABC):
    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def write(self, data: bytes, timeout_ms: int) -> int: ...


class UsbTransport(Transport):
    DEFAULT_VENDOR_ID = 0x04B8  # Seiko Epson Corp.
    DEFAULT_PRODUCT_ID = 0x0E20  # TM-m30

    def __init__(
        self,
        vendor_id: int = DEFAULT_VENDOR_ID,
        product_id: int = DEFAULT_PRODUCT_ID,
    ) -> None:
        self.vendor_id = vendor_id
        self.product_id = product_id
        self._dev: usb.core.Device | None = None
        self._out_ep: usb.core.Endpoint | None = None

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

    def write(self, data: bytes, timeout_ms: int) -> int:
        if self._out_ep is None:
            raise RuntimeError("USB transport not opened")
        return self._out_ep.write(data, timeout=timeout_ms)


class TcpTransport(Transport):
    DEFAULT_PORT = 9100

    def __init__(self, host: str, port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None

    def open(self) -> None:
        self._sock = socket.create_connection(
            (self.host, self.port), timeout=5
        )

    def close(self) -> None:
        if self._sock is not None:
            self._sock.shutdown(socket.SHUT_WR)
            self._sock.close()
            self._sock = None

    def write(self, data: bytes, timeout_ms: int) -> int:
        if self._sock is None:
            raise RuntimeError("TCP transport not opened")
        self._sock.settimeout(timeout_ms / 1000)
        self._sock.sendall(data)
        return len(data)
