#!/usr/bin/python3
import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path

import humanfriendly

B_TO_KBIT = 1024 // 8


@dataclass
class CropArea:
    w: int
    h: int
    x: int
    y: int

    @staticmethod
    def from_string(source: str) -> "CropArea":
        return CropArea(*map(int, source.split(":")))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("ep")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--crop", type=CropArea.from_string)
    parser.add_argument(
        "-t",
        "--target-size",
        required=True,
        type=lambda x: humanfriendly.parse_size(x, binary=True),
    )
    parser.add_argument("-f", "--force", action="store_true")
    return parser.parse_args()


def get_video_length(path: Path) -> float:
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
            "csv=p=0",
        ],
        stdout=subprocess.PIPE,
        check=True,
    )
    return float(status.stdout.decode())


def encode(
    input_path: Path,
    output_path: Path,
    target_size: int,
    crop: CropArea | None,
    test: bool,
) -> None:
    audio_bitrate = 128
    video_length = get_video_length(input_path)
    video_bitrate = target_size / B_TO_KBIT / video_length - audio_bitrate

    args = ["ffmpeg", "-y", "-i", str(input_path)]
    if crop:
        args += ["-vf", f"crop={crop.w}:{crop.h}:{crop.x}:{crop.y}"]
    if test:
        args += ["-to", "00:01:00"]
    args += ["-c:v", "libx264"]
    args += ["-preset", "slow"]
    args += ["-tune", "animation"]
    args += ["-b:v", f"{video_bitrate:0f}k"]
    args += ["-pass", "1"]
    args += ["-an"]
    args += ["-f", "rawvideo"]
    args += ["/dev/null"]
    subprocess.run(args, check=True)

    args = ["ffmpeg", "-y", "-i", str(input_path)]
    if crop:
        args += ["-vf", f"crop={crop.w}:{crop.h}:{crop.x}:{crop.y}"]
    if test:
        args += ["-to", "00:01:00"]
    args += ["-c:v", "libx264"]
    args += ["-preset", "slow"]
    args += ["-tune", "animation"]
    args += ["-b:v", f"{video_bitrate:0f}k"]
    args += ["-pass", "2"]
    args += ["-c:a", "aac"]
    args += ["-b:a", f"{audio_bitrate:0f}k"]
    args += [str(output_path)]
    subprocess.run(args, check=True)

    for path in list(Path(".").iterdir()):
        if "ffmpeg2pass" in path.stem:
            path.unlink()


def main():
    args = parse_args()

    source_video_path = next(
        (p for p in Path("source").iterdir() if p.stem == args.ep + "-src"),
        None,
    )
    if not source_video_path:
        raise RuntimeError("No video file found")

    target_video_path = Path(f"source/{args.ep}.mkv")
    if target_video_path.exists() and not args.force:
        raise RuntimeError(f'"{target_video_path}" exists')

    encode(
        source_video_path,
        target_video_path,
        target_size=args.target_size,
        crop=args.crop,
        test=args.test,
    )


if __name__ == "__main__":
    main()
