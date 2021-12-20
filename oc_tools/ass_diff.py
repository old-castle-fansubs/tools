from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ass_parser import AssEvent, AssFile

from oc_tools.util import first, last


class BaseChange:
    @property
    def sort_key(self) -> Any:
        raise NotImplementedError("not implemented")


@dataclass
class LineRemovedChange(BaseChange):
    event: AssEvent

    @property
    def sort_key(self) -> Any:
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
    def sort_key(self) -> Any:
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
    def sort_key(self) -> Any:
        return self.old_event.number

    def __str__(self) -> str:
        return f"Line #{self.old_event.number}\n    Fixed timing\n"


@dataclass
class LineAddedChange(BaseChange):
    after_event: AssEvent | None
    before_event: AssEvent | None
    new_event: AssEvent

    @property
    def sort_key(self) -> Any:
        if self.after_event:
            return self.after_event.number
        if self.before_event:
            return self.before_event.number - 1
        return -1

    def __str__(self) -> str:
        if self.after_event and self.before_event:
            return (
                f"Between line #{self.after_event.number} "
                f"and #{self.before_event.number}\n"
                "    Missing line →\n"
                f"    {self.new_event.text}\n"
            )
        if self.after_event:
            return (
                f"After #{self.after_event.number}\n"
                "    Missing line →\n"
                f"    {self.new_event.text}\n"
            )
        if self.before_event:
            return (
                f"Before #{self.before_event.number}\n"
                "    Missing line →\n"
                f"    {self.new_event.text}\n"
            )
        return "???\n" "    Missing line →\n" f"    {self.new_event.text}\n"


def collect_changes(a_ass: AssFile, b_ass: AssFile) -> Iterable[BaseChange]:
    handled_b_events: list[AssEvent] = []

    for event1 in a_ass.events:
        if event2 := first(
            event
            for event in b_ass.events
            if event1.text == event.text
            and event1.start == event.start
            and event1.end == event.end
            and event1.style_name == event.style_name
        ):
            pass

        elif event2 := first(
            event
            for event in b_ass.events
            if (
                event1.text == event.text
                and event1.style_name == event.style_name
                and (event1.start != event.start or event1.end != event.end)
            )
        ):
            yield LineChangedTimeChange(event1, event2)

        elif event2 := first(
            event
            for event in b_ass.events
            if (
                event1.start == event.start
                and event1.end == event.end
                and event1.style_name == event.style_name
                and event1.text != event.text
            )
        ):
            yield LineChangedTextChange(event1, event2)

        else:
            yield LineRemovedChange(event1)

        if event2:
            handled_b_events.append(event2)

    sorted_a_events = list(sorted(a_ass.events, key=lambda event: event.start))
    for event2 in b_ass.events:
        if event2 in handled_b_events:
            continue
        event1a = last(
            event for event in sorted_a_events if event.start < event2.start
        )
        event1b = first(
            event for event in sorted_a_events if event.start >= event2.start
        )
        yield LineAddedChange(event1a, event1b, event2)


def postprocess_ass(ass_file: AssFile, keep_newlines: bool) -> None:
    if not keep_newlines:
        for event in ass_file.events:
            event.text = event.text.replace(r"\N", " ")
