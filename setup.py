from pathlib import Path

from setuptools import setup

ROOT_DIR = Path(__file__).parent
SCRIPTS_DIR = ROOT_DIR / "oc_tools" / "scripts"
SCRIPT_FILES = [path for path in SCRIPTS_DIR.iterdir() if path.suffix == ".py"]
import sys

setup(
    author="rr-",
    author_email="rr-@sakuya.pl",
    name="OldCastle tools",
    packages=["oc_tools"],
    entry_points={
        "console_scripts": [
            f"oc-{path.stem.replace('_', '-')} = oc_tools.scripts.{path.stem}:main"
            for path in SCRIPT_FILES
        ]
    },
    install_requires=[
        "colorama",
        "gitpython",
        "humanfriendly",
        "fonttools",
        "ass_tag_parser",
        "pysubs2",
        "xdg",
    ],
)
