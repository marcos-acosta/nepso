import nepso
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "test" / "assets"

transport = nepso.TcpTransport("10.51.46.125")

with nepso.Printer(transport, throttle_ms=100) as p:
    p.execute(
        [
            nepso.Text("hello world"),
            nepso.Image(ASSETS / "test-img-1.png"),
            nepso.Image(ASSETS / "test-img-2.jpg"),
            nepso.Image(ASSETS / "test-img-3.png"),
            nepso.CutAndPrint(),
        ]
    )
