#!/usr/bin/env python3
import argparse
import re
import sys
from pathlib import Path

import ass_tag_parser
from pysubs2 import SSAFile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", default="-")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.file == "-":
        text = sys.stdin.read()
    else:
        text = Path(args.file).read_text()

    subs = SSAFile.from_string(text)
    lines = []
    for sub in subs:
        # skip furigana
        if sub.style.lower() == "rubi":
            continue

        text = ""
        for ass_item in ass_tag_parser.parse_ass(sub.text):
            if isinstance(ass_item, ass_tag_parser.AssText):
                text += ass_item.text

        for line in text.split("\\N"):
            line = re.sub(r"\(.*\)", "", line)  # actors
            line = re.sub("➡", "", line)  # line continuation
            line = re.sub("≪", "", line)  # distant dialogues
            line = re.sub("[＜＞《》]", "", line)
            line = re.sub("｡", "。", line)  # half-width period
            line = re.sub("([…！？])。", r"\1", line)  # superfluous periods
            line = line.rstrip("・")

            line = re.sub(" ", "", line)  # Japanese doesn't need spaces

            if line:
                lines.append(line)

    print("\n".join(lines))


if __name__ == "__main__":
    main()
