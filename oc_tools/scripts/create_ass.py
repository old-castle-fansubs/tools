#!/usr/bin/env python3
import argparse
import sys
from collections.abc import Iterable
from copy import copy
from pathlib import Path
from subprocess import PIPE, run

import lxml.etree
from ass_parser import AssEvent, AssFile, read_ass, write_ass

from oc_tools.util import str_to_ms, wrap_exceptions

VIDEO_EXTENSIONS = {".mkv", ".mp4"}
ASS_EXTENSIONS = {".ass"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, nargs="+")
    parser.add_argument(
        "-C",
        "--no-chapters",
        dest="copy_chapters",
        action="store_false",
        help="don't copy any chapters from video files",
    )
    parser.add_argument(
        "-S",
        "--no-styles",
        dest="copy_styles",
        action="store_false",
        help="don't copy any styles from subtitle files",
    )
    parser.add_argument(
        "-E",
        "--no-events",
        dest="copy_events",
        action="store_false",
        help="don't copy any events from subtitle files",
    )
    return parser.parse_args()


def extract_chapters(source_path: Path) -> Iterable[AssEvent]:
    out = run(
        ["mkvextract", source_path, "chapters", "-"], stdout=PIPE, check=True
    ).stdout
    if not out:
        return

    try:
        xml = lxml.etree.XML(out)
    except lxml.etree.XMLSyntaxError:
        print(
            f'Warning: no chapters found in "{source_path}"', file=sys.stderr
        )
        return

    for chapter_atom in xml.xpath("//ChapterAtom"):
        title = chapter_atom.xpath("string(.//ChapterString)")
        start = chapter_atom.xpath("string(.//ChapterTimeStart)")
        _end = chapter_atom.xpath("string(.//ChapterTimeEnd)")
        yield AssEvent(
            start=str_to_ms(start),
            end=str_to_ms(start),
            text=title,
            actor="[chapter]",
            is_comment=True,
        )


@wrap_exceptions
def main() -> None:
    args = parse_args()

    ass_file = AssFile()
    for source in args.source:
        if not source.exists():
            raise RuntimeError(f'File "{source}" does not exist.')

        if source.suffix in VIDEO_EXTENSIONS:
            ass_file.script_info.update(
                {"Video File": str(source), "Audio File": str(source)}
            )
            if ass_file.script_info.get("PlayResY") is None:
                ass_file.script_info["PlayResY"] = "288"

            if args.copy_chapters:
                for event in extract_chapters(source):
                    ass_file.events.append(event)

        elif source.suffix in ASS_EXTENSIONS:
            other_ass_file = read_ass(source)
            ass_file.script_info.update(other_ass_file.script_info.items())

            if args.copy_events:
                for event in other_ass_file.events:
                    if event.style_name.lower().startswith(
                        ("opening", "ending", "op", "ed", "lyrics", "karaoke")
                    ) or event.actor.startswith("["):
                        ass_file.events.append(copy(event))

            if args.copy_styles:
                ass_file.styles.clear()
                for style in other_ass_file.styles:
                    ass_file.styles.append(copy(style))

        else:
            raise RuntimeError(f'Don\'t know what to do with "{source}".')

    write_ass(ass_file, sys.stdout)


if __name__ == "__main__":
    main()
