#!/usr/bin/env python3.9
import argparse
import sys
from pathlib import Path

from ass_parser import read_ass

from oc_tools import ass_diff


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("dir1", type=Path)
    parser.add_argument("dir2", type=Path)
    parser.add_argument(
        "-n",
        action="store_true",
        dest="keep_newlines",
        help="don't convert newlines",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="print only file names"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    for path1 in sorted(args.dir1.iterdir(), key=lambda path: path.name):
        if path1.suffix != ".ass" or not path1.is_file():
            continue

        path2 = args.dir2 / path1.name
        if not path2.exists():
            print(f"{path1}: {path2} does not exist", file=sys.stderr)

        a_ass = read_ass(path1)
        b_ass = read_ass(path2)
        ass_diff.postprocess_ass(a_ass, keep_newlines=args.keep_newlines)
        ass_diff.postprocess_ass(b_ass, keep_newlines=args.keep_newlines)

        changes = list(ass_diff.collect_changes(a_ass, b_ass))
        if changes:
            print(f"{path1}: {path2} differs", file=sys.stderr)

        if not args.quiet:
            for change in sorted(changes, key=lambda change: change.sort_key):
                print(change)


if __name__ == "__main__":
    main()
