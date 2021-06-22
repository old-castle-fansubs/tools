import typing as T


def first(source: T.Iterable[T.Any]) -> T.Any:
    return next(source, None)


def last(source: T.Iterable[T.Any]) -> T.Any:
    item = None
    for item in source:
        pass
    return item
