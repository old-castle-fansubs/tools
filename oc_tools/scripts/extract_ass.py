#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from subprocess import PIPE, run
from typing import Any

from oc_tools.util import wrap_exceptions


class ExtractionError(Exception):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode")

    subs_parser = subparsers.add_parser("subs")
    subs_parser.add_argument("source", type=Path)
    subs_parser.add_argument(
        "-o", "--output", help="output file", type=Path, default="-"
    )
    subs_parser.add_argument(
        "--track-num", "-t", help="subs track number", type=int, default=0
    )

    attachments_parser = subparsers.add_parser("attachments")
    attachments_parser.add_argument("source", type=Path)
    attachments_parser.add_argument(
        "-o", "--output", help="output file", type=Path, default=Path(".")
    )

    return parser.parse_args()


def extract_track(source_path: Path, track_id: int) -> bytes:
    result = run(
        [
            "mkvextract",
            "tracks",
            "-r",
            "/dev/null",
            source_path,
            f"{track_id}:/dev/stdout",
        ],
        stdout=PIPE,
        check=True,
    )
    return result.stdout


def get_info(source_path: Path) -> Any:
    result = run(["mkvmerge", "-J", str(source_path)], check=True, stdout=PIPE)
    return json.loads(result.stdout.decode())


def extract_attachment(source_path: Path, attachment_id: int) -> bytes:
    result = run(
        [
            "mkvextract",
            "attachments",
            "-r",
            "/dev/null",
            source_path,
            f"{attachment_id}:/dev/stdout",
        ],
        check=True,
        stdout=PIPE,
    )
    return result.stdout


def extract_subtitles(
    source_path: Path, output_path: Path, track_num: int
) -> None:
    info = get_info(source_path)
    ass_track_ids: list[int] = [
        track["id"] for track in info["tracks"] if track["type"] == "subtitles"
    ]
    if not ass_track_ids:
        raise ExtractionError(f'no subtitles found in "{source_path}"')
    ass = extract_track(source_path, ass_track_ids[track_num]).decode()
    if str(output_path) == "-":
        print(ass, end="")
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(ass)


def extract_attachments(source_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    info = get_info(source_path)
    if not info["attachments"]:
        raise ExtractionError(f'no attachments found in "{source_path}"')
    for i, attachment in enumerate(info["attachments"]):
        target_path = output_dir / f"{i + 1}_{attachment['file_name']}"
        target_path.write_bytes(
            extract_attachment(source_path, attachment["id"])
        )
        print(
            f'Written {target_path.stat().st_size} bytes to "{target_path}"',
            file=sys.stderr,
        )


def check_deps() -> None:
    progs = ["mkvmerge", "mkvextract"]
    for prog in progs:
        try:
            run([prog, "-h"], check=True, stdout=PIPE, stderr=PIPE)
        except FileNotFoundError:
            raise ExtractionError(
                "please install mkvtoolnix before running this script"
            ) from None


@wrap_exceptions
def main() -> None:
    check_deps()
    args = parse_args()
    if args.mode == "subs":
        extract_subtitles(
            args.source.expanduser(), args.output.expanduser(), args.track_num
        )
    else:
        extract_attachments(args.source.expanduser(), args.output.expanduser())


if __name__ == "__main__":
    main()
