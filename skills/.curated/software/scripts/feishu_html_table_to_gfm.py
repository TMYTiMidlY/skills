#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# ///
"""Convert feishu2md HTML tables into GitHub-flavored Markdown tables."""
from __future__ import annotations

import argparse
import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path


BR_TOKEN = "\u0000BR\u0000"
TABLE_RE = re.compile(r"<table\b[^>]*>.*?</table>", re.S | re.I)


def clean_cell_text(text: str) -> str:
    text = text.replace(BR_TOKEN, "<br>")
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*", "<br>", text)
    return text.strip().replace("|", r"\|")


@dataclass
class TableState:
    rows: list[list[str]] = field(default_factory=list)
    current_row: list[str] = field(default_factory=list)
    current_cell: list[str] = field(default_factory=list)
    in_cell: bool = False
    in_row: bool = False
    in_table: bool = False


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.state = TableState()

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        tag = tag.lower()
        if tag == "table":
            self.state = TableState(in_table=True)
        elif tag == "tr" and self.state.in_table:
            self.state.in_row = True
            self.state.current_row = []
        elif tag in {"td", "th"} and self.state.in_row:
            self.state.in_cell = True
            self.state.current_cell = []
        elif tag == "br" and self.state.in_cell:
            self.state.current_cell.append(BR_TOKEN)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self.state.in_cell:
            cell = clean_cell_text("".join(self.state.current_cell))
            self.state.current_row.append(cell)
            self.state.current_cell = []
            self.state.in_cell = False
        elif tag == "tr" and self.state.in_row:
            if self.state.current_row:
                self.state.rows.append(self.state.current_row)
            self.state.current_row = []
            self.state.in_row = False
        elif tag == "table" and self.state.in_table:
            self.state.in_table = False

    def handle_data(self, data: str) -> None:
        if self.state.in_cell:
            self.state.current_cell.append(data)

    def handle_entityref(self, name: str) -> None:
        if self.state.in_cell:
            self.state.current_cell.append(html.unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        if self.state.in_cell:
            self.state.current_cell.append(html.unescape(f"&#{name};"))

    def render(self) -> str:
        if not self.state.rows:
            return ""

        width = max(len(row) for row in self.state.rows)
        rows = [row + [""] * (width - len(row)) for row in self.state.rows]
        header = rows[0]
        body = rows[1:]

        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(["---"] * width) + " |",
        ]
        lines.extend("| " + " | ".join(row) + " |" for row in body)
        return "\n".join(lines)


def convert_tables(md: str) -> str:
    def repl(match: re.Match[str]) -> str:
        parser = TableParser()
        parser.feed(match.group(0))
        parser.close()
        rendered = parser.render()
        return rendered if rendered else match.group(0)

    return TABLE_RE.sub(repl, md)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert HTML tables in feishu2md output to GitHub pipe tables."
    )
    parser.add_argument("input", type=Path, help="Markdown file from feishu2md")
    parser.add_argument("-o", "--output", type=Path, help="Output file path")
    parser.add_argument("--in-place", action="store_true", help="Overwrite input file")
    args = parser.parse_args()

    source = args.input.read_text(encoding="utf-8")
    converted = convert_tables(source)

    if args.in_place:
        args.input.write_text(converted, encoding="utf-8")
        return

    out_path = args.output or args.input.with_name(f"{args.input.stem}.gfm.md")
    out_path.write_text(converted, encoding="utf-8")


if __name__ == "__main__":
    main()
