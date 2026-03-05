"""
Delegate to main Strider CLI so that:

  python -m strider.migrations migrate
  python -m strider.migrations makemigrations

behave the same as:

  strider migrate
  strider makemigrations
"""

import sys
from strider.cli.main import main

if __name__ == "__main__":
    # Rewrite argv: python -m strider.migrations migrate -> strider migrate
    sys.argv = ["strider"] + sys.argv[2:]
    main()
