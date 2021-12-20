#!/usr/bin/env python3.8
import argparse
import re
from pathlib import Path

import git
from ass_parser import read_ass

from oc_tools import ass_diff
from oc_tools.util import wrap_exceptions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("commit", default="HEAD", nargs="?")
    parser.add_argument(
        "-n",
        action="store_true",
        dest="keep_newlines",
        help="don't convert newlines",
    )
    return parser.parse_args()


@wrap_exceptions
def main() -> None:
    args = parse_args()
    repo = git.Repo(search_parent_directories=True)

    commit1 = repo.commit(args.commit + "^")
    commit2 = repo.commit(args.commit)
    diff_index = commit1.diff(commit2)

    for diff_item in diff_index.iter_change_type("M"):
        if not all(
            [
                diff_item.a_blob.path.endswith(".ass"),
                diff_item.b_blob.path.endswith(".ass"),
            ]
        ):
            continue

        path = Path(diff_item.a_path).name
        match = re.search(r"(\d+)", path)
        if not match:
            raise ValueError(
                "Cannot infer episode number from filename {path.name}"
            )
        ep_number = int(match.group(1))
        header = f"Episode {ep_number:02d}"
        print(header)
        print("-" * len(header))
        print()

        a_blob = diff_item.a_blob.data_stream.read().decode("utf-8")
        b_blob = diff_item.b_blob.data_stream.read().decode("utf-8")

        a_ass = read_ass(a_blob)
        b_ass = read_ass(b_blob)
        ass_diff.postprocess_ass(a_ass, keep_newlines=args.keep_newlines)
        ass_diff.postprocess_ass(b_ass, keep_newlines=args.keep_newlines)

        for change in sorted(
            ass_diff.collect_changes(a_ass, b_ass),
            key=lambda change: change.sort_key,
        ):
            print(change)


if __name__ == "__main__":
    main()
