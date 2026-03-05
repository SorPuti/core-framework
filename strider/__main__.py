"""
Strider CLI entry point.

Usage:
    python -m strider [command] [options]

Examples:
    python -m strider init myproject
    python -m strider run
    python -m strider migrate
"""

from strider.cli.main import main

if __name__ == "__main__":
    main()
