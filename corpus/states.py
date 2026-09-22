"""Recover, from the documentation pages, the state each docs example runs against.

`docs-examples.json` holds question definitions lifted from the docs. The state
they were asked about was left behind, so the corpus judged every question with
nothing in front of it, which is not how any of them runs. This finds the state
beside each question on its own page and writes it back.

    python3 corpus/states.py [--pages=local/docs] [--write]

Without `--write` it reports coverage and changes nothing. Pages are the `.md`
sources under `local/docs`, fetched by `corpus/pages.py`.
"""
import ast, json, pathlib, re, sys

PAGES = next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith('--pages=')), 'local/docs')
WRITE = '--write' in sys.argv[1:]
NEAR = 8000

norm = lambda s: re.sub(r'\s+', ' ', s).strip()


def value_at(text, i):
    """The literal starting at i: a quoted string, or a balanced object."""
    while i < len(text) and text[i] == ' ':
        i += 1

    if i >= len(text):
        return None

    if text[i] in '"\'':
        quote, j = text[i], i + 1
        while j < len(text) and text[j] != quote:
            j += 2 if text[j] == '\\' else 1
        return text[i:j + 1]

    if text[i] == '{':
        depth = 0
        for j in range(i, min(len(text), i + 20000)):
            depth += (text[j] == '{') - (text[j] == '}')
            if depth == 0:
                return text[i:j + 1]

    # A bare name, resolved against an assignment elsewhere on the page.
    name = re.match(r'[A-Za-z_][A-Za-z0-9_]*', text[i:])

    return name.group(0) if name else None


def decode(literal, text):
    """A state literal as JSON, following one level of name if that is what it is."""
    if literal is None:
        return None

    if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', literal):
        found = re.search(re.escape(literal) + r'\s*=\s*', text)

        if found is None:
            return None

        literal = value_at(text, found.end())

        if literal is None or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', literal):
            return None

    try:
        value = json.loads(literal)
    except json.JSONDecodeError:
        # The pages carry JSON, Python and JSX, so a state can be a single-quoted
        # string or a Python dict. Anything that is neither is left behind.
        try:
            value = ast.literal_eval(literal)
        except (ValueError, SyntaxError):
            return None

    if not isinstance(value, (str, dict, list)):
        return None

    # A state built from names the page never spells out carries nothing.
    return value if value not in ('', {}, []) else None


def enclosing(text, at):
    """The smallest balanced object containing `at`, as (start, end)."""
    depth, start = 0, None

    for i in range(at, -1, -1):
        if text[i] == '}':
            depth += 1
        elif text[i] == '{':
            if depth == 0:
                start = i
                break
            depth -= 1

    if start is None:
        return None

    depth = 0

    for j in range(start, len(text)):
        depth += (text[j] == '{') - (text[j] == '}')

        if depth == 0:
            return (start, j + 1) if j >= at else None

    return None


def state_for(instructions, text):
    """The state written in the same example as this question.

    Nearest-in-the-page paired "How frustrated is the customer?" with a job
    posting, because the page shows several examples in a row. The state has to
    come from the object the question itself sits in
    """
    needle = norm(instructions)[:60]
    where = text.find(needle)

    if where < 0:
        return None

    scopes = []
    span = enclosing(text, where)

    # Outwards from the question: its own object, then the example around it.
    while span is not None:
        scopes.append(span)
        span = enclosing(text, span[0] - 1) if span[0] > 0 else None

    for start, end in scopes:
        block = text[start:end]

        if block.count(needle) != 1:
            # Two questions of the same wording in one scope cannot be told apart.
            continue

        for match in re.finditer(r'(?:"state"\s*:|\bstate\s*[:=])\s*', block):
            value = decode(value_at(block, match.end()), text)

            if value is not None:
                return value

    # A script assigns the state outside any object it shares with the question.
    behind = [m.end() for m in re.finditer(r'state\s*=\s*', text[max(0, where - NEAR):where])]

    return decode(value_at(text, max(0, where - NEAR) + behind[-1]), text) if behind else None


docs = json.loads(pathlib.Path('corpus/docs-examples.json').read_text())
pages = {}
found = 0

for key, entry in docs.items():
    page = pathlib.Path(PAGES) / f"{entry['page']}.md"

    if not page.is_file():
        print(f'  {key}: no page at {page}', file=sys.stderr)
        continue

    text = pages.setdefault(entry['page'], norm(page.read_text()))
    state = state_for(entry['instructions'] if isinstance(entry['instructions'], str)
                      else json.dumps(entry['instructions']), text)

    if state is None:
        continue

    entry['state'] = state
    found += 1

print(f'{found} of {len(docs)} docs examples now carry the state their page ran them against')

if WRITE:
    pathlib.Path('corpus/docs-examples.json').write_text(json.dumps(docs, indent=2, ensure_ascii=False) + '\n')
    print('written to corpus/docs-examples.json')
