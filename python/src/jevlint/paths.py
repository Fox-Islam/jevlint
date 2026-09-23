"""
Where this package was installed.

`checks/catalogue.json` and its translations are looked up from here, because a
path written from the source tree addresses nothing once the wheel is unpacked
somewhere else.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
