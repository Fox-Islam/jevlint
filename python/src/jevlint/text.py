"""
Every message the tool prints, in the reader's language.

Patterns are ICU MessageFormat, so a plural is chosen by the locale's CLDR rules
instead of by a `== 1` written here. English takes two forms and Polish four. A
locale file needs only the keys it translates, and the rest are read from
English, so a part-finished translation prints English.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, ClassVar

from .icu import PatternError
from .icu import format as _format
from .lang.en import MESSAGES
from .paths import HERE

_TAG = re.compile(r'^([a-zA-Z]{2,3})(?:_([a-zA-Z0-9]{2,4}))?$')


class Text:
    FALLBACK = 'en'

    _locale = FALLBACK

    _bundles: ClassVar[dict[str, dict[str, Any]]] = {}

    @classmethod
    def use(cls, locale: str | None) -> None:
        """
        The locale to answer in.

        A tag no file has falls back a step at a time, `fr_CA` to `fr` to
        English, so a missing `fr_CA` reaches French before it reaches English.
        """
        cls._locale = _normalise(locale) or cls.FALLBACK

    @classmethod
    def locale(cls) -> str:
        return cls._locale

    @classmethod
    def from_environment(cls) -> None:
        """
        Read the locale from the environment, for a run nobody told.

        `LC_ALL` outranks `LC_MESSAGES`, which outranks `LANG`, which is the
        order POSIX gives them.
        """
        for name in ('JEVLINT_LANG', 'LC_ALL', 'LC_MESSAGES', 'LANG'):
            value = os.environ.get(name)

            if value and _normalise(value) is not None:
                cls.use(value)

                return

        cls.use(None)

    @classmethod
    def of(cls, key: str, values: dict[str, Any] | None = None) -> str:
        """
        One message, formatted.

        A key no locale has prints as itself, which is findable by eye; an empty
        string is not. A pattern this cannot parse prints unformatted, so a
        translation with a stray brace loses its arguments and not the line.
        """
        pattern = cls._lookup(key)

        if not isinstance(pattern, str):
            return key

        try:
            return _format(cls._locale, pattern, values or {})
        except PatternError:
            return pattern

    @classmethod
    def list(cls, key: str) -> list[str]:
        """
        A list of words or phrases a check matches against.

        The locale's list and English are both returned. A query written in
        French can still name its options in English, and a check given only the
        French list would stop finding them.
        """
        mine = cls._lookup(key)
        english = [] if cls._locale == cls.FALLBACK else cls._bundle(cls.FALLBACK).get(key, [])
        merged = (mine if isinstance(mine, list) else []) + (english if isinstance(english, list) else [])

        return list(dict.fromkeys(word for word in merged if isinstance(word, str)))

    @classmethod
    def reset(cls) -> None:
        """Forget what is loaded, so a test can change locale inside one process."""
        cls._bundles = {}
        cls._locale = cls.FALLBACK

    @classmethod
    def _lookup(cls, key: str) -> Any:
        for locale in _candidates(cls._locale):
            bundle = cls._bundle(locale)

            if key in bundle:
                return bundle[key]

        return None

    @classmethod
    def _bundle(cls, locale: str) -> dict[str, Any]:
        loaded = cls._bundles.get(locale)

        if loaded is None:
            loaded = _read(locale)
            cls._bundles[locale] = loaded

        return loaded


def _candidates(locale: str) -> list[str]:
    """The locale, then what it falls back to, then English."""
    found = [locale]

    if '_' in locale:
        found.append(locale.split('_', 1)[0])

    found.append(Text.FALLBACK)

    return list(dict.fromkeys(found))


def _read(locale: str) -> dict[str, Any]:
    """
    A locale file, from `JEVLINT_LANG_DIR` before the shipped English, so a
    language nobody has contributed can be added without forking.

    Unlike `JEVLINT_CHECKS_DIR` this falls through to the shipped messages: a
    directory holding only `fr.json` is a translation and not a rule set, and
    English still has to be found behind it. The file is JSON and not Python,
    because a file dropped into a directory at run time is data and importing it
    would run it.
    """
    directory = os.environ.get('JEVLINT_LANG_DIR')

    if directory:
        path = Path(directory.rstrip('/')) / f'{locale}.json'

        if path.exists():
            try:
                parsed = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                # A locale file that will not parse is answered in English, the
                # same as one that does not exist. Failing here would take the
                # whole run down over the language it was going to print in.
                parsed = None

            if isinstance(parsed, dict):
                return parsed

    return dict(MESSAGES) if locale == Text.FALLBACK else {}


def _normalise(locale: str | None) -> str | None:
    """
    A language tag as the files are named: `fr_CA` from `fr_CA.UTF-8`, `fr-ca` or
    `fr_ca`. `C` and `POSIX` name no language and are read as none.
    """
    if locale is None:
        return None

    tag = re.sub(r'[.@].*$', '', locale.strip()).replace('-', '_')
    named = _TAG.match(tag)

    if named is None:
        return None

    language = named.group(1).lower()

    if language in ('c', 'posix'):
        return None

    return language if named.group(2) is None else f'{language}_{named.group(2).upper()}'


class CheckText:
    """
    What a check reports about your query, in the reader's language.

    These live beside the catalogue and not in `lang/`, because the catalogue is
    not Python: an implementation in another language reads the same file. A
    locale with no file, or a check with no entry in it, is answered from the
    catalogue.

    The question a model check puts to Jev is never read from here. Translating
    it would change what the check measures, and every number in
    docs/evidence.md was taken with the wording in the catalogue.
    """

    # What a translation may replace. `question`, `trigger` and `docs` are not
    # words about a query.
    FIELDS = ('title', 'message', 'hint', 'suggest')

    _loaded: ClassVar[dict[str, dict[str, dict[str, str]]]] = {}

    @classmethod
    def for_check(cls, check_id: str) -> dict[str, str]:
        """
        The fields a translation replaces for one check, in the order Text reads
        its locales, so a region file wins over its language.
        """
        found: dict[str, str] = {}

        for locale in _overlay_locales():
            for field, text in cls._bundle(locale).get(check_id, {}).items():
                if field not in found and field in cls.FIELDS:
                    found[field] = text

        return found

    @classmethod
    def reset(cls) -> None:
        cls._loaded = {}

    @classmethod
    def _bundle(cls, locale: str) -> dict[str, dict[str, str]]:
        already = cls._loaded.get(locale)

        if already is not None:
            return already

        path = _locate_overlay(locale)
        overlay: dict[str, dict[str, str]] = {}

        if path is not None:
            for check_id, fields in json.loads(Path(path).read_text(encoding='utf-8')).items():
                if isinstance(fields, dict):
                    overlay[check_id] = {
                        field: text for field, text in fields.items() if isinstance(text, str)
                    }

        cls._loaded[locale] = overlay

        return overlay


def _overlay_locales() -> list[str]:
    locale = Text.locale()

    if locale == Text.FALLBACK:
        return []

    return [locale, locale.split('_', 1)[0]] if '_' in locale else [locale]


def _locate_overlay(locale: str) -> str | None:
    directory = os.environ.get('JEVLINT_CHECKS_DIR')
    candidates = []

    if directory:
        candidates.append(Path(directory.rstrip('/')) / 'lang' / f'{locale}.json')

    candidates.append(HERE / 'checks' / 'lang' / f'{locale}.json')
    candidates.append(HERE.parents[2] / 'checks' / 'lang' / f'{locale}.json')

    return next((str(path) for path in candidates if path.is_file()), None)
