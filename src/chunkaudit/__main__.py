"""Allows ``python -m chunkaudit`` as an alternative to the installed console script."""

import sys

from .cli import main

sys.exit(main())
