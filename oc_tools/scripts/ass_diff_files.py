#!/usr/bin/env python3.9
import argparse
from pathlib import Path

from bubblesub.fmt.ass.reader import read_ass

from oc_tools import ass_diff


def parse_args() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file1", type=Path)
    parser.add_argument("file2", type=Path)
    parser.add_argument(
        "-n",
        action="store_true",
        dest="keep_newlines",
        help="don't convert newlines",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    a_ass = read_ass(args.file1)
    b_ass = read_ass(args.file2)
    ass_diff.postprocess_ass(a_ass, keep_newlines=args.keep_newlines)
    ass_diff.postprocess_ass(b_ass, keep_newlines=args.keep_newlines)

    changes = list(ass_diff.collect_changes(a_ass, b_ass))
    for change in sorted(changes, key=lambda change: change.sort_key):
        print(change)

    if changes:
        exit(1)
    exit(0)


if __name__ == "__main__":
    main()
