"""Test script: print a small receipt via the Printer class."""

from printer import CutAndPrint, Printer, Text


def main() -> None:
    items = [
        Text("Hello from nepso!\n"),
        Text("USB test print OK.\n\n\n"),
        CutAndPrint(),
    ]
    with Printer() as printer:
        written = printer.execute(items)
    print(f"Wrote {written} bytes")


if __name__ == "__main__":
    main()
