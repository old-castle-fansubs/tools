import re
import sys
from collections.abc import Callable, Iterable, Iterator
from typing import Any, TypeVar

T = TypeVar("T")


def first(source: Iterator[T]) -> T | None:
    return next(source, None)


def last(source: Iterator[T]) -> T | None:
    item = None
    for item in source:
        pass
    return item


def wrap_exceptions(func: Callable[[], None]) -> Callable[[], None]:
    def wrapped():
        try:
            func()
        except Exception as ex:
            print(ex, file=sys.stderr)

    return wrapped


def str_to_ms(text: str) -> int:
    """Convert a human readable text in form of `[[-]HH:]MM:SS.mmm` to PTS.

    :param text: input text
    :return: PTS
    """
    result = re.match(
        """
        ^(?P<sign>[+-])?
        (?:(?P<hour>\\d+):)?
        (?P<minute>\\d\\d):
        (?P<second>\\d\\d)\\.
        (?P<millisecond>\\d\\d\\d)\\d*$
        """.strip(),
        text.strip(),
        re.VERBOSE,
    )

    if not result:
        raise ValueError(f'invalid time format: "{text}"')

    sign = result.group("sign")
    hour = int(result.group("hour"))
    minute = int(result.group("minute"))
    second = int(result.group("second"))
    millisecond = int(result.group("millisecond"))
    ret = ((((hour * 60) + minute) * 60) + second) * 1000 + millisecond
    if sign == "-":
        ret = -ret
    return ret
