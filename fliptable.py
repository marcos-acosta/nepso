"""Read every row from the `dbs` postgres table and print each as a card.

Connection comes from $DATABASE_URL, or libpq defaults (PG* env vars) if unset.
"""

import argparse
import os
from dataclasses import dataclass
from datetime import datetime

import psycopg
import questionary
from psycopg.rows import class_row

from printer import CutAndPrint, Printable, Printer, Text, Image, Justification

CARD_WIDTH = 48
STAT_MAX = 10

SELECT_SQL = (
    "SELECT id, name, db_name, short_description, storage, "
    "availability, consistency, read_speed, write_speed, "
    "logged_at, will_present FROM dbs ORDER BY logged_at ASC"
)


@dataclass
class DbRow:
    id: str
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
    ]
    if row.will_present:
        body.extend(["", "* presented"])
    body.extend(["", ""])
    return [
        Text("FLIP TABLE;\n"),
        Image("/Users/marcos/m/projects/fliptable/branding/flip.png"),
        Text("\n".join(body)),
        Image(
            "/Users/marcos/m/projects/fliptable/qr-code.png",
            width_dots=128,
            justification=Justification.CENTER,
        ),
        Text("https://fliptable.nyc", justification=Justification.CENTER),
        Text("\n\n"),
        CutAndPrint(),
    ]


def _fmt_logged_at(logged_at: datetime | None) -> str:
    if logged_at is None:
        return "—"
    return f"{logged_at:%Y-%m-%d %I:%M:%S %p}"


def _list(rows: list[DbRow]) -> list[Printable]:
    rule = "─" * CARD_WIDTH
    lines = ["FLIP TABLE;", "database registry", "", rule]
    for row in rows:
        marker = "  * presenting" if row.will_present else ""
        lines.append(f"{row.name} :: {row.db_name}{marker}")
        lines.append("")
        lines.append(row.short_description)
        lines.append("")
        ts = _fmt_logged_at(row.logged_at)
        lines.append(ts)
        lines.append(row.id)
        lines.append(rule)
    lines.extend(["", ""])
    return [Text("\n".join(lines) + "\n"), CutAndPrint()]


def _dsn() -> str:
    return os.environ.get("DATABASE_URL") or "postgresql:///postgres"


def fetch_rows() -> list[DbRow]:
    with psycopg.connect(_dsn()) as conn:
        with conn.cursor(row_factory=class_row(DbRow)) as cur:
            cur.execute(SELECT_SQL)
            return cur.fetchall()


def _parse_alignment(s: str) -> tuple[float, float] | None:
    try:
        xs, ys = s.split(",", 1)
        return float(xs.strip()), float(ys.strip())
    except (ValueError, AttributeError):
        return None


def run_detail(copies: int) -> None:
    with psycopg.connect(_dsn()) as conn:
        with conn.cursor(row_factory=class_row(DbRow)) as cur:
            cur.execute(SELECT_SQL)
            rows = cur.fetchall()
        by_id = {row.id: row for row in rows}

        with Printer() as printer:
            while True:
                choices = [
                    questionary.Choice(title=f"{r.name} ({r.db_name})", value=r.id)
                    for r in rows
                ]
                db_id = questionary.select("Select a database:", choices=choices).ask()

                while True:
                    raw = questionary.text("Alignment (e.g. '-0.43,0.2'):").ask()
                    if raw is None:
                        return
                    parsed = _parse_alignment(raw)
                    if parsed is not None:
                        break
                    print("  expected 'x,y' floats")
                x, y = parsed

                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE dbs SET alignment_x = %s, alignment_y = %s WHERE id = %s",
                        (x, y, db_id),
                    )
                conn.commit()

                row = by_id[db_id]
                for i in range(copies):
                    written = printer.execute(_card(row))
                    print(f"  copy {i + 1}/{copies} ({row.name}): {written} bytes")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["list", "detail"], nargs="?", default="detail")
    parser.add_argument(
        "-n",
        "--copies",
        type=int,
        default=1,
        help="copies per card in detail mode",
    )
    args = parser.parse_args()

    if args.mode == "list":
        rows = fetch_rows()
        print(f"Printing list of {len(rows)} database(s)...")
        with Printer() as printer:
            written = printer.execute(_list(rows))
            print(f"  {written} bytes")
    else:
        run_detail(copies=args.copies)


if __name__ == "__main__":
    main()
