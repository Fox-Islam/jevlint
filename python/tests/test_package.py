import ast
import re
import subprocess
import sys

import tomllib
from conftest import ROOT

from jevlint.console.application import Application

MANIFEST = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']

SOURCES = sorted((ROOT / 'python/src/jevlint').rglob('*.py'))


def test_the_version_the_tool_prints_is_the_version_the_package_publishes():
    """
    `jevlint --version` printed 0.1.0 from a tag that said 1.0.0, because nothing
    read both. A report carries this number, so a run checked by one build and
    reported as another is the thing it makes untraceable.
    """
    assert MANIFEST['version'] == Application.VERSION


def test_the_version_the_tool_prints_is_not_behind_the_newest_release_tag():
    if not (ROOT / '.git').exists():
        # A published sdist has no tags to read. Nothing to compare.
        return

    try:
        printed = subprocess.run(
            ['git', '-C', str(ROOT), 'tag', '--sort=-v:refname'],
            capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return

    tags = [tag for tag in printed.split('\n') if re.fullmatch(r'v?\d+\.\d+\.\d+', tag)]

    if len(tags) == 0:
        return

    newest = [int(part) for part in tags[0].lstrip('v').split('.')]
    mine = [int(part) for part in Application.VERSION.split('.')]

    # Ahead is fine: the constant is bumped, then the tag is cut. Behind means a
    # release went out printing an older number than it is.
    assert mine >= newest, (
        f'jevlint --version prints {Application.VERSION}, behind the tag {tags[0]}.'
    )


def test_the_package_names_the_sdk_and_the_cldr_data_and_nothing_else():
    """
    A package that installs what it does not name works on the machine it was
    built on and fails on the next one.
    """
    names = sorted(re.split(r'[<>=!~\[ ]', name)[0] for name in MANIFEST['dependencies'])

    assert names == ['babel', 'typesafe-sdk']


def test_the_package_imports_nothing_it_does_not_name():
    # `httpx2` and `pydantic` are the SDK's own: the client wraps a transport and
    # a response model from each, which is why both are reached directly.
    allowed = sys.stdlib_module_names | {'babel', 'typesafe_sdk', 'httpx2', 'pydantic'}
    undeclared = set()

    for path in SOURCES:
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Import):
                undeclared |= {alias.name.split('.')[0] for alias in node.names} - allowed

            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
                undeclared |= {node.module.split('.')[0]} - allowed

    assert undeclared == set()


def test_the_package_ships_the_catalogue_which_is_read_by_every_implementation():
    build = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['tool']['hatch']['build']
    wheel = build['targets']['wheel']

    assert wheel['force-include']['checks'] == 'jevlint/checks', (
        'A published package with no catalogue checks nothing.'
    )
    assert wheel['packages'] == ['python/src/jevlint']
    assert '/spec' in build['targets']['sdist']['include']


def test_the_package_points_its_script_at_something_that_runs():
    from jevlint.console.application import main

    assert MANIFEST_SCRIPTS['jevlint'] == 'jevlint.console.application:main'
    assert callable(main)


MANIFEST_SCRIPTS = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['scripts']
