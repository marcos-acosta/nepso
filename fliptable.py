"""Read every row from the `dbs` postgres table and print each as a card.

Connection comes from $DATABASE_URL, or libpq defaults (PG* env vars) if unset.
"""

import os
from dataclasses import dataclass
from datetime import datetime

import psycopg
from psycopg.rows import class_row

from printer import CutAndPrint, Printable, Printer, Text, Image

CARD_WIDTH = 48
STAT_MAX = 10


@dataclass
class DbRow:
    name: str
    db_name: str
    short_description: str
    storage: int
    availability: int
    consistency: int
    read_speed: int
    write_speed: int
    logged_at: datetime | None
    will_present: bool


def _bar(value: int) -> str:
    n = max(0, min(STAT_MAX, value))
    return "█" * n + "░" * (STAT_MAX - n) + f" {value:>2}"


def _card(row: DbRow) -> list[Printable]:
    rule = "─" * CARD_WIDTH
    body = [
        rule,
        f"{row.db_name} - {row.name}",
        rule,
        row.short_description,
        "",
        f"storage      {_bar(row.storage)}",
        f"availability {_bar(row.availability)}",
        f"consistency  {_bar(row.consistency)}",
        f"read speed   {_bar(row.read_speed)}",
        f"write speed  {_bar(row.write_speed)}",
        "",
    ]
    if row.logged_at is not None:
        body.append(f"logged: {row.logged_at:%Y-%m-%d %I:%M:%S %p}")
    body.extend(["", "", ""])
    return [
        Text("FLIP TABLE;\n"),
        Image("/Users/marcos/m/art/fliptable/flip.png"),
        Text("\n".join(body)),
        Image("/Users/marcos/m/projects/fliptable/qr-code.png", width_dots=128),
        Text("\n"),
        CutAndPrint(),
    ]


def fetch_rows() -> list[DbRow]:
    dsn = os.environ.get("DATABASE_URL") or "postgresql:///postgres"
    with psycopg.connect(dsn) as conn:
        with conn.cursor(row_factory=class_row(DbRow)) as cur:
            cur.execute(
                "SELECT name, db_name, short_description, storage, "
                "availability, consistency, read_speed, write_speed, "
                "logged_at, will_present FROM dbs ORDER BY name"
            )
            return cur.fetchall()


def main() -> None:
    rows = fetch_rows()
    print(f"Printing {len(rows)} card(s)...")
    with Printer() as printer:
        for row in rows:
            written = printer.execute(_card(row))
            print(f"  {row.name}: {written} bytes")


if __name__ == "__main__":
    main()
