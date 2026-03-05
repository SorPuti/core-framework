"""
Delegate to main Stride CLI so that:

  python -m stride.migrations migrate
  python -m stride.migrations makemigrations

behave the same as:

  stride migrate
  stride makemigrations
"""

import sys
from stride.cli.main import main

if __name__ == "__main__":
    # Rewrite argv: python -m stride.migrations migrate -> stride migrate
    sys.argv = ["stride"] + sys.argv[2:]
    main()
