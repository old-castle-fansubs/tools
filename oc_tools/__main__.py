#!/usr/env/bin python3.9
from oc_tools.scripts.base import BaseScript

all_scripts = [cls() for cls in BaseScript.__subclasses__()]

def main() -> None:
    pass

if __name__ == '__main__':
    main()
