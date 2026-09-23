"""`python -m jevlint`, for a checkout with no console script on the PATH."""
from .console.application import main

raise SystemExit(main())
