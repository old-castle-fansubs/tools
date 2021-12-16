#!/usr/bin/python3
import argparse
import contextlib
import itertools
import re
import shelve
import subprocess
import typing as T
import zlib
from dataclasses import dataclass
from pathlib import Path

import ass_tag_parser
import fontTools.ttLib as font_tools
import pysubs2
import xdg


def ms_to_str(ms: int) -> str:
    return pysubs2.time.ms_to_str(ms, fractions=True)


def pairwise(source: T.Iterable[T.Any]) -> T.Iterable[T.Any]:
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = itertools.tee(source)
    next(b, None)
    return zip(a, b)


TT_NAME_ID_FONT_FAMILY = 1
TT_NAME_ID_FULL_NAME = 4
TT_NAME_ID_TYPOGRAPHIC_FAMILY = 16
TT_PLATFORM_MICROSOFT = 3

SHELVE_PATH = Path(xdg.XDG_CACHE_HOME) / "oc-tools.dat"
FONT_DIRS = [
    Path(xdg.XDG_CONFIG_HOME) / "oc-fonts",
    Path("~/.local/share/fonts").expanduser(),
    Path("/usr/share/fonts/TTF"),
    Path("/usr/share/fonts/OTF"),
]


def get_iso_639_2_lang_code(lang: str) -> str:
    lang = lang.lower().replace("_", "-")
    if lang in {"en", "eng", "en-us"}:
        return "eng"
    if lang in {"pl", "pol", "pl-pl"}:
        return "pol"
    if lang in {"ro", "ro-ro"}:
        return "rum"
    if lang in {"nl", "nl-nl"}:
        return "dut"
    raise ValueError(f"unknown language {lang}")


def single(source: T.Iterable[T.Any]) -> T.Any:
    unique = set(source)
    if len(unique) != 1:
        raise ValueError("expected unique value")
    return next(iter(unique))


@dataclass
class Subtitles:
    path: Path
    info: T.Dict[str, str]
    styles: T.Dict[str, T.Any]
    lines: T.List[T.Any]

    @staticmethod
    def from_path(path: Path) -> "Subtitles":
        subs = pysubs2.SSAFile.load(path)
        return Subtitles(
            path=path,
            info=dict(subs.info),
            styles=subs.styles,
            lines=list(subs),
        )

    @property
    def language(self) -> str:
        return get_iso_639_2_lang_code(self.info.get("Language", "en_US"))


@dataclass
class Video:
    path: Path
    length: int

    @staticmethod
    def from_path(path: Path) -> "Video":
        return Video(path=path, length=Video.get_video_length(path))

    @staticmethod
    def get_video_length(path: Path) -> int:
        status = subprocess.run(
            [
                "ffprobe",
                "-i",
                str(path),
                "-show_entries",
                "format=duration",
                "-v",
                "quiet",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
            ],
            stdout=subprocess.PIPE,
        )
        if status.returncode != 0:
            raise RuntimeError("Error while getting video length")
        return int(float(status.stdout.decode().strip()) * 1000)


@dataclass
class StyleInfo:
    family: str
    weight: int
    is_italic: bool

    def __hash__(self) -> int:
        return hash((self.family, self.weight, self.is_italic))


@dataclass
class ChapterTitle:
    text: str
    language: str


@dataclass
class Chapter:
    start_time: int
    end_time: int
    is_hidden: bool
    titles: T.List[ChapterTitle]


@dataclass
class Font:
    names: T.List[str]
    is_bold: bool
    is_italic: bool

    @staticmethod
    def from_path(font_path: Path) -> "Font":
        font = font_tools.TTFont(font_path)
        names: T.List[str] = []

        for record in font["name"].names:
            if (
                record.nameID
                in {
                    TT_NAME_ID_FONT_FAMILY,
                    TT_NAME_ID_FULL_NAME,
                    TT_NAME_ID_TYPOGRAPHIC_FAMILY,
                }
                and record.platformID == TT_PLATFORM_MICROSOFT
            ):
                names.append(record.string.decode("utf-16-be"))

        return Font(
            names=names,
            is_bold=bool(font["OS/2"].fsSelection & (1 << 5)),
            is_italic=bool(font["OS/2"].fsSelection & 1),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("ep")
    parser.add_argument("-v", "--version", type=int, default=1)
    return parser.parse_args()


def mux(
    title: str,
    video: Video,
    subs: T.List[Subtitles],
    chapters_path: T.Optional[Path],
    font_paths: T.Set[Path],
    output_path: Path,
) -> None:
    mux_args = [
        "mkvmerge",
        "--title",
        title,
        "-o",
        str(output_path),
        str(video.path),
    ]

    for sub in subs:
        mux_args.extend(["--language", f"0:{sub.language}", str(sub.path)])

    if chapters_path:
        mux_args.extend(["--chapters", str(chapters_path)])

    for font_path in font_paths:
        mux_args.extend(
            [
                "--attachment-mime-type",
                "application/x-truetype-font",
                "--attach-file",
                str(font_path),
            ]
        )

    status = subprocess.run(mux_args)
    if status.returncode != 0:
        raise RuntimeError("Error while muxing")


def get_title(subs: Subtitles) -> str:
    return subs.info["Title"]


def get_group_name(subs: Subtitles) -> str:
    return subs.info.get("Group", "OldCastle").replace(" & ", "-")


def get_chapters(subs: T.List[Subtitles], video: Video) -> T.Iterable[Chapter]:
    lines: T.Dict[int, T.Dict[str, str]] = {}
    for sub in subs:
        for line in sub.lines:
            if line.name == "[chapter]":
                title = "".join(
                    chunk.text
                    for chunk in ass_tag_parser.parse_ass(line.text)
                    if isinstance(chunk, ass_tag_parser.AssText)
                )
                if line.start not in lines:
                    lines[line.start] = {}
                lines[line.start][sub.language] = title

    lines[video.length] = {}

    for ((start_time, titles), (end_time, _)) in pairwise(lines.items()):
        if any(text.startswith("#") for lang, text in titles.items()):
            continue
        if any(text.startswith("$") for lang, text in titles.items()):
            titles = {lang: text[1:] for lang, text in titles.items()}
            is_hidden = True
        else:
            is_hidden = False

        yield Chapter(
            start_time=start_time,
            end_time=end_time,
            is_hidden=is_hidden,
            titles=[
                ChapterTitle(language=language, text=text)
                for (language, text) in titles.items()
            ],
        )


def create_chapters_file(chapters: T.Iterable[Chapter]) -> T.Optional[Path]:
    chapters = list(chapters)
    if not chapters:
        return None
    chapters_path = Path("chapters.tmp")
    with chapters_path.open("w", encoding="utf-8") as handle:
        handle.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        handle.write('<!DOCTYPE Chapters SYSTEM "matroskachapters.dtd">\n')
        handle.write("<Chapters>\n")
        handle.write("\t<EditionEntry>\n")
        handle.write("\t\t<EditionFlagDefault>1</EditionFlagDefault>\n")
        handle.write("\t\t<EditionFlagOrdered>1</EditionFlagOrdered>\n")
        handle.write("\t\t<EditionFlagHidden>0</EditionFlagHidden>\n")
        for chapter in chapters:
            handle.write("\t\t<ChapterAtom>\n")
            handle.write(
                "\t\t\t<ChapterTimeStart>{start_time}</ChapterTimeStart>\n"
                "\t\t\t<ChapterTimeEnd>{end_time}</ChapterTimeEnd>\n"
                "\t\t\t<ChapterFlagEnabled>{enabled:d}</ChapterFlagEnabled>\n"
                "\t\t\t<ChapterFlagHidden>{is_hidden:d}</ChapterFlagHidden>\n".format(
                    enabled=True,
                    start_time=ms_to_str(chapter.start_time),
                    end_time=ms_to_str(chapter.end_time),
                    is_hidden=chapter.is_hidden,
                )
            )
            for title in chapter.titles:
                handle.write(
                    "\t\t\t<ChapterDisplay>\n"
                    "\t\t\t\t<ChapterString>{text}</ChapterString>\n"
                    "\t\t\t\t<ChapterLanguage>{language}</ChapterLanguage>\n"
                    "\t\t\t</ChapterDisplay>\n".format(
                        text=title.text, language=title.language
                    )
                )
            handle.write("\t\t</ChapterAtom>\n")
        handle.write("\t</EditionEntry>\n")
        handle.write("</Chapters>")
    return chapters_path


def change_crc(path: Path, checksum: int) -> None:
    tmp_path = Path("tmp.dat")
    status = subprocess.run(
        ["crcmanip", "patch", path, "-o", tmp_path, "%08x" % checksum]
    )
    if status.returncode != 0:
        raise RuntimeError("Error while patching CRC")
    path.unlink()
    tmp_path.rename(path)


def bold_to_weight(value: T.Union[int, bool]) -> int:
    if value is True or value == 1:
        return 700
    if value is False or value == 0:
        return 400
    assert isinstance(value, int)
    return value


def get_used_font_styles(subs: Subtitles) -> T.Iterable[StyleInfo]:
    style_name_to_style_info = {
        style_name: StyleInfo(
            style.fontname, bold_to_weight(style.bold), style.italic
        )
        for style_name, style in subs.styles.items()
    }

    used_font_styles = set()
    for i, line in enumerate(subs.lines):
        if line.is_comment:
            continue

        style_info = style_name_to_style_info[line.style]
        try:
            used_font_styles.add(style_info)
        except KeyError as ex:
            print(f"Invalid style at line #{i + 1}: {line.style}")

        weight = style_info.weight
        is_italic = style_info.is_italic

        try:
            ass_line = ass_tag_parser.parse_ass(line.text)
        except ass_tag_parser.errors.BaseError as ex:
            print(f"Error parsing line #{i + 1} ({line.text}): {ex}")
            continue

        for ass_item in ass_line:
            if isinstance(ass_item, ass_tag_parser.AssTagBold):
                if ass_item.enabled is not None:
                    weight = 700 if ass_item.enabled else 400
                else:
                    weight = ass_item.weight
            elif isinstance(ass_item, ass_tag_parser.AssTagItalic):
                is_italic = ass_item.enabled
            elif (
                isinstance(ass_item, ass_tag_parser.AssTagFontName)
                and ass_item.name is not None
            ):
                used_font_styles.add(
                    StyleInfo(ass_item.name, weight, is_italic)
                )

        used_font_styles.add(
            StyleInfo(
                family=style_info.family, weight=weight, is_italic=is_italic
            )
        )

    return used_font_styles


def get_fonts(font_paths: T.Iterable[Path]) -> T.Dict[Path, Font]:
    with shelve.open(str(SHELVE_PATH)) as cache:
        fonts = {}
        for font_path in font_paths:
            cache_key = "font-" + str(font_path.resolve())
            font = cache.get(cache_key, None)
            if not font:
                try:
                    font = Font.from_path(font_path)
                except Exception:
                    continue
                cache[cache_key] = font
            fonts[font_path] = font
        return fonts


def filter_fonts(
    used_font_styles: T.Iterable[StyleInfo], font_paths: T.Iterable[Path]
) -> T.Set[Path]:
    fonts = get_fonts(font_paths)

    ret: T.Set[Path] = set()
    for style in sorted(used_font_styles, key=lambda s: s.family):
        candidates = []
        for font_path, font in fonts.items():
            if style.family.lower() in [n.lower() for n in font.names]:
                weight = (font.is_bold == (style.weight > 400)) + (
                    font.is_italic == style.is_italic
                )
                candidates.append((weight, font_path))
        candidates.sort(key=lambda i: -i[0])

        print(
            f"({style.family}, {style.weight}, {style.is_italic})".ljust(40),
            end=" -> ",
        )

        if candidates:
            selected_font_path = candidates[0][1]
            ret.add(selected_font_path)
            print('"{}"'.format(selected_font_path.resolve()))
        else:
            print("-")

    return ret


def get_incremental_crc32(handle: T.IO[bytes]) -> int:
    ret = 0
    chunk = handle.read(1024)
    if len(chunk):
        ret = zlib.crc32(chunk)
        while True:
            chunk = handle.read(1024)
            if len(chunk) > 0:
                ret = zlib.crc32(chunk, ret)
            else:
                break
    ret &= 0xFFFFFFFF
    return ret


def get_checksum(version: int, episode: int, paths: T.Iterable[Path]) -> int:
    checksum = 0
    for path in sorted(paths):
        with path.open("rb") as handle:
            path_checksum = get_incremental_crc32(handle)
        print(f"{path_checksum:08X} {path}")
        checksum ^= path_checksum & 0xFFFF0000
    checksum |= version << 12
    try:
        checksum |= int(episode)
    except ValueError:
        pass
    return checksum


@contextlib.contextmanager
def header(title: str) -> T.Any:
    print(title)
    yield
    print()
    print()


def get_subs_paths(episode: str) -> T.List[Path]:
    found: T.List[Path] = []
    for path in Path().iterdir():
        if (
            path.stem == episode
            or path.stem.startswith(f"{episode}-")
            or path.stem.endswith(f"-{episode}")
        ):
            found.append(path)
    if not found:
        raise RuntimeError("No subs file found")
    return found


def get_video_path(episode: str) -> Path:
    for path in Path("source").iterdir():
        if path.stem == episode:
            return path
    raise RuntimeError("No video file found")


def sort_subs(subs: T.Iterable[Subtitles]) -> T.Iterable[Subtitles]:
    lang_priorities = ["eng", "pol"]

    other_subs = list(
        sorted(
            (sub for sub in subs if sub.language not in lang_priorities),
            key=lambda sub: sub.language,
        )
    )

    priority_subs = list(
        sorted(
            (sub for sub in subs if sub.language in lang_priorities),
            key=lambda sub: lang_priorities.index(sub.language),
        )
    )

    return priority_subs + other_subs


def main() -> None:
    args = parse_args()
    episode = args.ep
    version = args.version

    subs = list(map(Subtitles.from_path, get_subs_paths(episode)))
    video = Video.from_path(get_video_path(episode))

    subs = sort_subs(subs)

    with header("Collecting fonts"):
        available_font_paths: T.List[Path] = []
        for directory in FONT_DIRS:
            if directory.exists():
                available_font_paths += list(directory.iterdir())

        if not available_font_paths:
            raise RuntimeError("No fonts found")

        used_font_styles: T.List[StyleInfo] = list(
            sum([list(get_used_font_styles(sub)) for sub in subs], [])
        )
        source_font_paths = filter_fonts(
            used_font_styles, available_font_paths
        )

    with header("Collecting chapters"):
        chapters = list(get_chapters(subs, video))
        for i, chapter in enumerate(chapters):
            flags = "-H"[chapter.is_hidden]
            print(
                f"{i:2d}. {flags} "
                f"{ms_to_str(chapter.start_time)}.."
                f"{ms_to_str(chapter.end_time)}"
            )
            for title in chapter.titles:
                print(f"  - [{title.language}] {title.text}")
        temp_chapters_path = create_chapters_file(chapters)

    with header("Collecting metadata"):
        group_name = single(map(get_group_name, subs))
        eng_subs = [sub for sub in subs if sub.language == "eng"]
        pol_subs = [sub for sub in subs if sub.language == "pol"]
        title = single(map(get_title, eng_subs if len(eng_subs) else pol_subs))

    with header("Computing target checksum"):
        all_paths: T.Set[Path] = (
            set([sub.path for sub in subs] + [video.path]) | source_font_paths
        )
        if temp_chapters_path:
            all_paths.add(temp_chapters_path)

        checksum = get_checksum(version, episode, all_paths)
        target_video_path = Path(
            f"[{group_name}] {title} [{checksum:08X}].mkv"
        )

    with header("Muxing"):
        mux(
            title,
            video,
            subs,
            temp_chapters_path,
            source_font_paths,
            target_video_path,
        )
        if temp_chapters_path and temp_chapters_path.exists():
            temp_chapters_path.unlink()

    with header("Adjusting output CRC32"):
        change_crc(target_video_path, checksum)


if __name__ == "__main__":
    main()
