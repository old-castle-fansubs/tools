#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
from subprocess import run

TARGET_HOST = "oc"
TARGET_DIR = "srv/website/data/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    run(
        [
            "rsync",
            "-ahsv",
            "--progress",
            args.source,
            f"{TARGET_HOST}:{TARGET_DIR}",
        ],
        stdout=sys.stderr.fileno(),
        check=True,
    )

    run(
        [
            "ssh",
            TARGET_HOST,
            "cd srv/website; "
            f"docker-compose run --rm app manage prepare_featured_image '{args.source.name}'",
        ],
        stdout=sys.stderr.fileno(),
        check=True,
    )


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as ex:
        print(ex, file=sys.stderr)

