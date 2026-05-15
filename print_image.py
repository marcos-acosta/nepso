"""Print an image file on the receipt printer.

Usage: `uv run print_image.py <path>`
"""

import sys

from printer import CutAndPrint, Image, Printer


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: print_image.py <path>")
    with Printer() as p:
        p.execute([Image(sys.argv[1]), CutAndPrint()])


if __name__ == "__main__":
    main()
