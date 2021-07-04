#!/usr/bin/env python3.9
import typing as T
from collections import OrderedDict
from pathlib import Path

import colorama
import xdg

DATA_PATH = Path(xdg.XDG_CONFIG_HOME) / "oc-progress.txt"


def uniq(source: T.Iterable[T.Any]) -> T.Iterable[T.Any]:
    return list(OrderedDict.fromkeys(source))


def split(source: str, delim: str) -> T.List[str]:
    return list(map(str.strip, source.split(delim)))


class AnimeProgress:
    def __init__(
        self, title: str, episodes: T.Dict[T.Tuple[int, str, str], bool]
    ) -> None:
        self.title = title
        self.episodes = episodes

        self.min_episode = min(
            ep for ep, category, state in self.episodes.keys()
        )
        self.max_episode = max(
            ep for ep, category, state in self.episodes.keys()
        )
        self.categories = uniq(
            category for ep, category, state in self.episodes.keys()
        )
        self.category_steps = {
            category: uniq(
                state
                for ep, ep_category, state in self.episodes.keys()
                if category == ep_category
            )
            for category in self.categories
        }

        self.finished = all(
            self.get_state(ep, category="release", step="Release")
            for ep in range(self.min_episode, self.max_episode + 1)
        )

    def get_category_steps(self, category: str) -> T.Optional[T.List[str]]:
        return self.category_steps.get(category)

    def get_state(self, ep: int, category: str, step: str) -> bool:
        return self.episodes.get((ep, category, step), None)


def get_progress() -> T.Iterable[AnimeProgress]:
    with DATA_PATH.open("r", encoding="utf-8") as handle:
        lines = [
            line
            for line in map(str.strip, handle)
            if line and not line.startswith("#")
        ]

        while lines:
            title = lines.pop(0)

            category_steps_map: T.Dict[str, T.List[str]] = {}

            while lines and "|" not in lines[0]:
                category_line = lines.pop(0)
                category, steps_line = split(category_line, ":")
                category_steps_map[category] = split(steps_line, ",")
            category_steps_map["release"] = ["Release"]

            episode_states: T.Dict[T.Tuple[int, str, str]] = {}
            while lines and "|" in lines[0]:
                state_line = lines.pop(0)

                ep, *category_state_lines = split(state_line, "|")
                ep = int(ep)

                for (category, category_steps), category_state in zip(
                    category_steps_map.items(), category_state_lines
                ):
                    for step, char in zip(category_steps, category_state):
                        episode_states[ep, category, step] = (
                            char.lower() == "x"
                        )

            yield AnimeProgress(title=title, episodes=episode_states)


def get_step_title(step: str, category: str) -> str:
    if category == "release":
        return "Release"
    return f"[{category.upper()}] {step}"


def print_progress_header(anime: AnimeProgress, longest_title: int) -> None:
    print(anime.title.ljust(longest_title), end=" ")
    for ep in range(anime.min_episode, anime.max_episode + 1):
        idx = ep - anime.min_episode
        if idx % 10 == 0:
            print(str(ep).ljust(12), end=" ")
    print()


def print_progress_step(
    anime: AnimeProgress, category: str, step: str, longest_title: int
) -> None:
    if category.upper() == "PL":
        print(colorama.Style.BRIGHT + colorama.Fore.RED, end="")
    elif category.upper() == "EN":
        print(colorama.Style.BRIGHT + colorama.Fore.GREEN, end="")
    elif category.lower() == "release":
        print(colorama.Style.BRIGHT + colorama.Fore.BLUE, end="")
    else:
        print(colorama.Style.RESET_ALL, end="")
    print(
        get_step_title(step, category).ljust(longest_title),
        end=" ",
    )

    for ep in range(anime.min_episode, anime.max_episode + 1):
        idx = ep - anime.min_episode
        if anime.get_state(ep, category, step):
            print(colorama.Style.BRIGHT + colorama.Fore.GREEN, end="")
            print("\N{BLACK SQUARE}", end="")
        else:
            print(colorama.Fore.BLACK, end="")
            print("\N{WHITE SQUARE}", end="")
        if idx % 5 == 4:
            print(" ", end="")
        if idx % 10 == 9:
            print(" ", end="")
    print(colorama.Style.RESET_ALL)


def print_progress(progress: T.Iterable[AnimeProgress]) -> None:
    longest_title = max(
        max((len(anime.title), len(get_step_title(step, category))))
        for anime in progress
        for category in anime.categories
        for step in anime.get_category_steps(category)
    )

    for anime in progress:
        print_progress_header(anime, longest_title)

        for category in anime.categories:
            for step in anime.get_category_steps(category):
                print_progress_step(anime, category, step, longest_title)

        print()


def main() -> None:
    progress = list(get_progress())
    print_progress([anime for anime in progress if not anime.finished])


if __name__ == "__main__":
    main()