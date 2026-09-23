"""
The Python page names methods by hand, and a renamed one leaves a page that reads
as though it were right.
"""
import re

from conftest import ROOT

import jevlint
from jevlint.linter import Linter

PAGE = (ROOT / 'docs/python.md').read_text(encoding='utf-8')


def test_the_python_page_names_only_methods_something_here_has():
    # Every class the package exports, because the page moves between a linter, a
    # query and a report and each name has to exist on one of them.
    has = {
        name
        for exported in jevlint.__all__
        for name in dir(getattr(jevlint, exported))
        if not name.startswith('_')
    }
    # `.only(` and `.check(` in the page, and `Linter.make(` with its class. The
    # transport in the worked example is the SDK's and not this package's.
    named = set(re.findall(r'\.([a-zA-Z_]+)\(', PAGE))

    assert sorted(named - has - {'Response', 'MockTransport'}) == []


def test_the_python_page_names_only_things_the_package_exports():
    for name in ('Linter', 'Query', 'Client', 'Config', 'Severity', 'Report'):
        assert name in jevlint.__all__, f'The page names {name} and the package does not export it.'


def test_the_python_page_names_the_static_factories_it_says_start_a_linter():
    for name in ('make', 'from_environment', 'rules_only'):
        assert hasattr(Linter, name), f'The page names Linter.{name} and there is none.'
        assert f'Linter.{name}(' in PAGE


def test_every_link_in_the_python_page_resolves_to_a_file_that_is_there():
    broken = [
        target for target in re.findall(r'\]\(([^)#\s]+)(?:#[^)\s]*)?\)', PAGE)
        if not target.startswith(('http', 'mailto:'))
        and not (ROOT / 'docs' / target).resolve().exists()
    ]

    assert broken == []
