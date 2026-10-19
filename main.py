# -*- coding: utf-8 -*-
#
# this is the entry point, run this file
# the rest of the code lives in the codepacker package, the start-up is in codepacker/ui/app.py
# "--version" prints the version and exits without opening a window (the exe answers it too)

import sys

from codepacker import APP_NAME, __version__
from codepacker.ui.app import run


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    if "--version" in arguments:
        print("{} {}".format(APP_NAME, __version__))
        return 0
    return run()


if __name__ == "__main__":
    sys.exit(main())
