"""Allow ``python -m trading_assistant ...`` as a shorter form of ``python -m trading_assistant.cli ...``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
