import typing as T
from dataclasses import dataclass

from bubblesub.fmt.ass.event import AssEvent
from bubblesub.fmt.ass.file import AssFile
from bubblesub.fmt.ass.reader import read_ass

from oc_tools.util import first, last


class BaseChange:
    @property
    def sort_key(self) -> T.Any:
        raise NotImplementedError("not implemented")


@dataclass
class LineRemovedChange(BaseChange):
    event: AssEvent

    @property
    def sort_key(self) -> T.Any:
        return self.event.number

    def __str__(self) -> str:
        return (
            f"Line #{self.event.number}\n"
            f"    {self.event.text} →"
            f"\n    Removed\n"
        )


@dataclass
class LineChangedTextChange(BaseChange):
    old_event: AssEvent
    new_event: AssEvent

    @property
    def sort_key(self) -> T.Any:
        return self.old_event.number

    def __str__(self) -> str:
        return (
            f"Line #{self.old_event.number}\n"
            f"    {self.old_event.text} →\n"
            f"    {self.new_event.text}\n"
        )


@dataclass
class LineChangedTimeChange(BaseChange):
    old_event: AssEvent
    new_event: AssEvent

    @property
    def sort_key(self) -> T.Any:
        return self.old_event.number

    def __str__(self) -> str:
        return f"Line #{self.old_event.number}\n    Fixed timing\n"


@dataclass
class LineAddedChange(BaseChange):
    after_event: AssEvent
    before_event: AssEvent
    new_event: AssEvent

    @property
    def sort_key(self) -> T.Any:
        return self.after_event.number

    def __str__(self) -> str:
        return (
            f"Between line #{self.after_event.number} "
            f"and #{self.before_event.number}\n"
            f"    Missing line →\n"
            f"    {self.new_event.text}\n"
        )


def collect_changes(a_ass: AssFile, b_ass: AssFile) -> T.Iterable[BaseChange]:
    handled_b_events: T.Set[AssEvent] = set()

    for event1 in a_ass.events:
        if event2 := first(
            e
            for e in b_ass.events
            if event1.text == e.text
            and event1.start == e.start
            and event1.end == e.end
            and event1.style == e.style
        ):
            pass

        elif event2 := first(
            e
            for e in b_ass.events
            if (
                event1.text == e.text
                and event1.style == e.style
                and (event1.start != e.start or event1.end != e.end)
            )
        ):
            yield LineChangedTimeChange(event1, event2)

        elif event2 := first(
            e
            for e in b_ass.events
            if (
                event1.start == e.start
                and event1.end == e.end
                and event1.style == e.style
                and event1.text != e.text
            )
        ):
            yield LineChangedTextChange(event1, event2)

        else:
            yield LineRemovedChange(event1)

        if event2:
            handled_b_events.add(event2)

    sorted_a_events = list(sorted(a_ass.events, key=lambda e: e.start))
    for event2 in b_ass.events:
        if event2 in handled_b_events:
            continue
        event1a = last(e for e in sorted_a_events if e.start < event2.start)
        event1b = first(e for e in sorted_a_events if e.start >= event2.start)
        yield LineAddedChange(event1a, event1b, event2)

def postprocess_ass(ass_file: AssFile, keep_newlines: bool) -> None:
    if not keep_newlines:
        for event in ass_file.events:
            event.text = event.text.replace(r"\N", " ")

