# Answering in another language

Jev takes a query in any language, so a query written in French is a query this
checks. Two things have to follow it: the words the tool prints, and the words the
checks match against. Only the second can turn a clean query into a finding.

English ships. Nothing else does yet, and a locale with no file is answered in English.

## Choosing a locale

`--lang=<locale>` on any command, or `JEVLINT_LANG`, then `LC_ALL`, `LC_MESSAGES`, `LANG`,
in that order. A tag falls back a step at a time, so `fr_CA` reaches `fr` before it reaches
English, and `C` or `POSIX` names no language and is read as none.

## Adding one

A locale is one PHP file returning a map of key to pattern, named for the tag:

```php
<?php // fr.php

return [
    'report.nothing_to_report' => 'Rien à signaler.',
    'skipped.jev_not_asked' => 'Jev n\'a pas été interrogé, donc {count, plural, one {# vérification n\'a} other {# vérifications n\'ont}} pas été exécutée{count, plural, one {} other {s}}.',
];
```

Put it in `php/lang/`, or anywhere and point `JEVLINT_LANG_DIR` at the directory. That
directory is read before the shipped one and does not replace it, so a file holding only
`fr.php` is a translation and English is still found behind it. **A locale needs only the
keys it translates**; anything absent is read from English, so a part-finished file prints
English and never a key. `php/lang/en.php` is the list to work from.

Patterns are [ICU MessageFormat](https://unicode-org.github.io/icu/userguide/format_parse/messages/),
so a plural is chosen by the locale's own CLDR rules instead of by a rule written in PHP.
English takes two forms and Polish four, and the pattern names which:

```php
'{count, plural, one {# sprawdzenie} few {# sprawdzenia} many {# sprawdzeń} other {# sprawdzenia}}'
```

A literal `{` or `}` is quoted with apostrophes, and a run of them is quoted together:
`'{'` gives one brace and `'}}'` gives two. Quoting them one at a time puts `''` in the
middle, which ICU reads as a literal apostrophe. A lone apostrophe before an ordinary
letter is already literal, so `the SDK's` needs nothing.

Two tests hold the file to its job: every pattern has to parse and leave no argument
unfilled, and every key the source asks for has to exist.

## What a check reports about your query

A check's `title`, `message`, `hint` and `suggest` live in the catalogue, not in
`php/lang/`, because the catalogue is not PHP and an implementation in another language
reads the same file. They are translated in `checks/lang/<locale>.json`, keyed by check id:

```json
{
  "choice/no-fallback": {
    "title": "Le Choice n'a pas d'option de repli",
    "suggest": "Ajoutez `\"autre\": \"Tout ce que les autres options ne couvrent pas\"`."
  }
}
```

`JEVLINT_CHECKS_DIR` covers this file too, in a `lang/` beside `catalogue.json`.

**The question a model check puts to Jev is never translated.** It is what the check
measures, and every figure in [evidence.md](evidence.md) was taken with the wording in the
catalogue; a translated question is a different check with the same id and no
measurements. `docs`, `trigger` and the check id are left alone for the same kind of
reason. A test asserts a translation cannot reach `question`.

## The words a check matches against

This is the half that changes findings instead of wording. Three lists are language
data, not display text:

| | what reads it |
| --- | --- |
| `words.fallback_labels` | `choice/no-fallback`, and the type inference that treats a catch-all as evidence of a Choice |
| `words.catch_all_phrases` | the same checks, reading what an option's description covers |
| `words.grammar` | `question/instruction-is-id`, which subtracts grammar to see whether an instruction adds anything to its id |

A French Choice offering `autre` has a catch-all. Against the English list alone,
`choice/no-fallback` fires on it and tells you to add the option that is already there.
With `words.fallback_labels` translated, it clears.

**The locale's list and English are both read.** A query written in French can still name
its options in English, and a check given only the French list would stop finding those.

Instructions are normalised with `\p{L}` and `mb_strtolower` instead of `[a-z]` and
`strtolower`, so an accented word survives instead of being cut into the pieces between
its accents.
