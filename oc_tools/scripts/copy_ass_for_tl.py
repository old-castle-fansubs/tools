#!/usr/bin/env python3
import argparse
import re
import sys
from collections.abc import Callable, Iterable
from copy import copy
from pathlib import Path
from subprocess import PIPE, run

import ass_parser
import lxml.etree

from oc_tools.util import str_to_ms, wrap_exceptions

ASS_EXTENSIONS = {".ass"}


def parse_language(language: str) -> str:
    if not re.fullmatch(r"\w+-\w+", language):
        raise ValueError("language: expected lang-locale format (e.g. en-us)")
    return language


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, nargs="+")
    parser.add_argument(
        "-b",
        "--base",
        type=Path,
        help="base pair of translated and untranslated file to guess karaoke and chapters from",
        required=True,
        nargs=2,
    )
    parser.add_argument("-l", "--language", type=parse_language)
    return parser.parse_args()


def read_ass(path: Path) -> ass_parser.AssFile:
    if not path.exists():
        raise RuntimeError(f'File "{path}" does not exist.')

    if path.suffix != ".ass":
        raise RuntimeError(f'File "{path}" is not an ASS file.')

    return ass_parser.read_ass(path)


def make_ass_template(
    src_ass_file: ass_parser.AssFile,
    meta_override: dict[str, str],
    chapter_map: dict[str, str],
    karaoke_map: dict[str, str],
    series_title_map: dict[str, str],
) -> ass_parser.AssFile:
    new_ass_file = ass_parser.AssFile()

    # meta
    new_ass_file.script_info.update(src_ass_file.script_info.items())
    new_ass_file.script_info.update(meta_override)

    # styles
    new_ass_file.styles.clear()
    for style in src_ass_file.styles:
        new_ass_file.styles.append(copy(style))

    # events
    for event in src_ass_file.events:
        new_event = copy(event)

        if is_event_chapter(event) and event.text in chapter_map:
            new_event.text = chapter_map[event.text]

        elif is_event_karaoke(event) and event.text in karaoke_map:
            new_event.text = karaoke_map[event.text]

        elif is_event_series_title(event) and event.text in series_title_map:
            new_event.text = series_title_map[event.text]

        else:
            new_event.note = new_event.text
            new_event.text = ""

        new_ass_file.events.append(new_event)

    return new_ass_file


def create_event_map(
    src_ass_file: ass_parser.AssFile,
    dst_ass_file: ass_parser.AssFile,
    key: Callable[[ass_parser.AssEvent], bool],
) -> dict[str, str]:
    src_events = [event for event in src_ass_file.events if key(event)]
    dst_events = [event for event in dst_ass_file.events if key(event)]
    mapping: dict[str, str] = {}
    for src_event, dst_event in zip(src_events, dst_events):
        mapping[src_event.text] = dst_event.text
    return mapping


def is_event_chapter(event: ass_parser.AssEvent) -> bool:
    return event.actor == "[chapter]"


def is_event_karaoke(event: ass_parser.AssEvent) -> bool:
    return event.actor == "[karaoke]"


def is_event_series_title(event: ass_parser.AssEvent) -> bool:
    return event.actor == "[series title]"


def create_chapter_map(
    src_ass_file: ass_parser.AssFile, dst_ass_file: ass_parser.AssFile
) -> dict[str, str]:
    return create_event_map(src_ass_file, dst_ass_file, key=is_event_chapter)


def create_karaoke_map(
    src_ass_file: ass_parser.AssFile, dst_ass_file: ass_parser.AssFile
) -> dict[str, str]:
    return create_event_map(src_ass_file, dst_ass_file, key=is_event_karaoke)


def create_series_title_map(
    src_ass_file: ass_parser.AssFile, dst_ass_file: ass_parser.AssFile
) -> dict[str, str]:
    return create_event_map(
        src_ass_file, dst_ass_file, key=is_event_series_title
    )


def get_meta_override(ass_file: ass_parser.AssEvent) -> dict[str, str]:
    meta_to_copy = ["Title", "Language"]
    mapping: dict[str, str] = {}
    for key in meta_to_copy:
        if ass_file and (value := ass_file.script_info.get(key)):
            mapping[key] = value
    return mapping


def get_language_from_path(path: Path) -> str:
    match = re.match(r"(\w+)-\d+", path.stem)
    assert match
    return match.group(1)


def get_ep_number_from_path(path: Path) -> str:
    match = re.match(r"\w+-(\d+)", path.stem)
    assert match
    return match.group(1)


@wrap_exceptions
def main() -> None:
    args = parse_args()

    assert get_language_from_path(args.base[0]) != get_language_from_path(
        args.base[1]
    )

    if get_language_from_path(args.base[1]) == get_language_from_path(
        args.source[0]
    ):
        args.base[1], args.base[0] = args.base[0], args.base[1]
    ref_src_ass_path = args.base[0]
    ref_dst_ass_path = args.base[1]

    ref_src_ass_file = read_ass(ref_src_ass_path)
    ref_dst_ass_file = read_ass(ref_dst_ass_path)

    meta_override = get_meta_override(ref_dst_ass_file)
    chapter_map = create_chapter_map(ref_src_ass_file, ref_dst_ass_file)
    karaoke_map = create_karaoke_map(ref_src_ass_file, ref_dst_ass_file)
    series_title_map = create_series_title_map(
        ref_src_ass_file, ref_dst_ass_file
    )

    for src_path in args.source:
        src_ass_file = read_ass(src_path)
        new_ass_file = make_ass_template(
            src_ass_file,
            meta_override,
            chapter_map,
            karaoke_map,
            series_title_map,
        )
        dst_path = (
            src_path.parent
            / f"{get_language_from_path(ref_dst_ass_path)}-{get_ep_number_from_path(src_path)}.ass"
        )
        dst_path.write_text(ass_parser.write_ass(new_ass_file))


if __name__ == "__main__":
    main()
