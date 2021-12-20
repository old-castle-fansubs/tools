#!/usr/bin/python3
import argparse
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")


def most_common(lst: list[T]) -> T:
    return max(set(lst), key=lst.count)


@dataclass
class CropArea:
    w: int
    h: int
    x: int
    y: int

    def __hash__(self) -> int:
        return hash((self.w, self.h, self.x, self.y))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("ep")
    return parser.parse_args()


def detect_crop_area(path: Path) -> Iterable[CropArea]:
    result = subprocess.run(
        [
            "ffmpeg",
            "-i",
            path,
            "-to",
            "00:01:00",
            "-vf",
            "cropdetect",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    for match in re.finditer(r"crop=(\d+):(\d+):(\d+):(\d+)", result.stderr):
        yield CropArea(*map(int, match.groups()))


def main():
    args = parse_args()

    source_video_path = next(
        (p for p in Path("source").iterdir() if p.stem == args.ep + "-src"),
        None,
    )
    if not source_video_path:
        raise RuntimeError("No video file found")

    crop = most_common(list(detect_crop_area(source_video_path)))
    print(f"{crop.w}:{crop.h}:{crop.x}:{crop.y}")


if __name__ == "__main__":
    main()
