#!/usr/bin/env python3
import argparse
from pathlib import Path

from ass_parser import read_ass
from ass_tag_parser import ass_to_plaintext

from oc_tools.util import wrap_exceptions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, nargs="+")
    return parser.parse_args()


@wrap_exceptions
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
    main()
