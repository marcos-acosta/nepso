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
    "logged_at, will_present, alignment_x, alignment_y "
    "FROM dbs ORDER BY logged_at ASC"
)

WINNER_QUADRANT_SQL = (
    "SELECT name, db_name, "
    "(POWER(ABS(alignment_x) - 1, 2) + POWER(ABS(alignment_y) - 1, 2)) AS score "
    "FROM dbs WHERE {where} ORDER BY score DESC LIMIT 1"
)

WINNER_ORIGIN_SQL = (
    "SELECT name, db_name, "
    "(POWER(alignment_x, 2) + POWER(alignment_y, 2)) AS score "
    "FROM dbs WHERE alignment_x IS NOT NULL AND alignment_y IS NOT NULL "
    "ORDER BY score ASC LIMIT 1"
)

QUADRANTS: list[tuple[str, str]] = [
    ("lawful good", "alignment_x >= 0 AND alignment_y >= 0"),
    ("chaotic good", "alignment_x <= 0 AND alignment_y >= 0"),
    ("chaotic evil", "alignment_x <= 0 AND alignment_y <= 0"),
    ("lawful evil", "alignment_x >= 0 AND alignment_y <= 0"),
]

ALIGNMENT_BUCKETS_X = 20  # 0.1-wide buckets across [-1, 1]
ALIGNMENT_BUCKETS_Y = 8  # 0.25-wide buckets (char cells are taller than wide)

ALIGNMENT_LABEL_LEFT = "chaotic"
ALIGNMENT_LABEL_RIGHT = "lawful"
ALIGNMENT_LABEL_TOP = "good"
ALIGNMENT_LABEL_BOTTOM = "evil"

ALIGNMENT_EXTRA_PADDING_LEFT = 3


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
    alignment_x: float | None
    alignment_y: float | None


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
    body.append("")
    body.extend(_alignment_chart_lines(row))
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


def _bucket_x(v: float) -> int:
    return max(0, min(ALIGNMENT_BUCKETS_X - 1, round((v + 1.0) * 10)))


def _bucket_y(v: float) -> int:
    return max(0, min(ALIGNMENT_BUCKETS_Y - 1, round((v + 1.0) * 4)))


def _alignment_chart_lines(row: DbRow) -> list[str]:
    grid = [[" "] * ALIGNMENT_BUCKETS_X for _ in range(ALIGNMENT_BUCKETS_Y)]
    if row.alignment_x is not None and row.alignment_y is not None:
        col = _bucket_x(float(row.alignment_x))
        # Y is inverted: y=+1 (good) goes to the top row (index 0).
        r = ALIGNMENT_BUCKETS_Y - 1 - _bucket_y(float(row.alignment_y))
        grid[r][col] = "*"

    pad = " " * (ALIGNMENT_EXTRA_PADDING_LEFT + len(ALIGNMENT_LABEL_LEFT) + 1)
    chart_w = ALIGNMENT_BUCKETS_X
    midline = ALIGNMENT_BUCKETS_Y // 2

    lines = [pad + " " + ALIGNMENT_LABEL_TOP.center(chart_w)]
    lines.append(pad + "┌" + "─" * chart_w + "┐")
    for r, row_chars in enumerate(grid):
        left = (
            (" " * ALIGNMENT_EXTRA_PADDING_LEFT) + f"{ALIGNMENT_LABEL_LEFT} "
            if r == midline
            else pad
        )
        right = f" {ALIGNMENT_LABEL_RIGHT}" if r == midline else ""
        lines.append(f"{left}│{''.join(row_chars)}│{right}")
    lines.append(pad + "└" + "─" * chart_w + "┘")
    lines.append(pad + " " + ALIGNMENT_LABEL_BOTTOM.center(chart_w))
    return lines


def _winners_printable(winners: list[tuple[str, str, str]]) -> list[Printable]:
    rule = "─" * CARD_WIDTH
    lines = ["FLIP TABLE;", "winners", "", rule]
    for label, name, db_name in winners:
        lines.append(label)
        lines.append(f"{name} :: {db_name}")
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


def run_winners() -> None:
    winners: list[tuple[str, str, str]] = []
    with psycopg.connect(_dsn()) as conn:
        with conn.cursor() as cur:
            for label, where in QUADRANTS:
                cur.execute(WINNER_QUADRANT_SQL.format(where=where))
                row = cur.fetchone()
                if row is not None:
                    winners.append((label, row[0], row[1]))
            cur.execute(WINNER_ORIGIN_SQL)
            row = cur.fetchone()
            if row is not None:
                winners.append(("most balanced", row[0], row[1]))

    for label, name, db_name in winners:
        print(f"  {label}: {name} ({db_name})")

    with Printer() as printer:
        written = printer.execute(_winners_printable(winners))
        print(f"  {written} bytes")


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

                parsed: tuple[float, float] | None = None
                while True:
                    raw = questionary.text(
                        "Alignment (e.g. '-0.43,0.2', empty to keep current):"
                    ).ask()
                    if raw is None:
                        return
                    if raw.strip() == "":
                        break
                    p = _parse_alignment(raw)
                    if p is not None:
                        parsed = p
                        break
                    print("  expected 'x,y' floats")

                row = by_id[db_id]
                if parsed is not None:
                    x, y = parsed
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE dbs SET alignment_x = %s, alignment_y = %s "
                            "WHERE id = %s",
                            (x, y, db_id),
                        )
                    conn.commit()
                    row.alignment_x = x
                    row.alignment_y = y

                for i in range(copies):
                    written = printer.execute(_card(row))
                    print(f"  copy {i + 1}/{copies} ({row.name}): {written} bytes")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=["list", "detail", "winners"], nargs="?", default="detail"
    )
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
    elif args.mode == "winners":
        run_winners()
    else:
        run_detail(copies=args.copies)


if __name__ == "__main__":
    main()
