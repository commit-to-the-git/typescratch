"""Allow running TypeScratch as `python -m typescratch build ...`.

This file is executed when you run `python -m typescratch` — it delegates
to the CLI's main function.
"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
