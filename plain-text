#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

from bubblesub.fmt.ass.reader import read_ass
from bubblesub.fmt.ass.util import ass_to_plaintext


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, nargs="+")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    for source in args.source:
        if not source.exists():
            raise RuntimeError(f'File "{source}" does not exist.')

        ass_file = read_ass(source)
        for event in ass_file.events:
            if not event.actor.startswith("["):
                print(ass_to_plaintext(event.text).replace("\n", " "))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as ex:
        print(ex, file=sys.stderr)
