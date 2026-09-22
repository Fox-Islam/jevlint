"""Build the query files harvest.py reads, from the three labelled source files.

The sources hold one question per entry, each with its label attached. A query file
holds the questions grouped as jevlint takes them, with the labels stripped, because a
label is evidence about a question and not part of it.

No query file carries a state. `harvest.py` runs `--no-state`, so the state-scoped
checks are never asked and a state would change nothing it records.

    python3 corpus/build.py [outdir]     # default local/corpus
"""
import json, pathlib, sys

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'local/corpus')

# Everything else in a source entry is the label: who says this question is right or
# wrong, and where they say it.
QUESTION = ('type', 'instructions', 'criteria')

# measure.py splits a score id on the first '/' into file stem and question id, so a
# question id must survive the trip without gaining one.
def ident(name):
    return name.replace('/', '_').replace('#', '_').replace('-', '_')


def question(entry, where):
    q = {k: entry[k] for k in QUESTION if k in entry}
    t = q.get('type')
    assert t in ('noul', 'choice', 'score'), f'{where}: type {t!r}'
    assert isinstance(q.get('instructions'), (str, dict, list)), f'{where}: no instructions'
    c = q.get('criteria')
    if c is not None:
        if t == 'choice':
            assert isinstance(c, dict) and len(c) >= 2, f'{where}: choice criteria'
        elif t == 'score':
            assert isinstance(c, list) and 2 <= len(c) <= 10, f'{where}: score criteria'
        else:
            assert isinstance(c, dict) and set(c) <= {'true', 'false'}, f'{where}: noul criteria'
    return q


def load(name):
    return json.loads(pathlib.Path(f'corpus/{name}.json').read_text())


files = {}
states = {}

# The gold and docs tiers are one file each; measure.py reads the stem as the tier.
files['gold'] = {ident(k): question(v, k) for k, v in load('gold').items()}

# A state belongs to one request, so questions asked against different states
# cannot share a file. The docs tier splits: one file per state recovered from
# the page, and one holding the questions whose page computes its state at run
# time and so carries none here.
docs = load('docs-examples')
by_state = {}

for k, v in docs.items():
    if 'state' not in v:
        files.setdefault('docs_ex', {})[ident(k)] = question(v, k)
        continue

    key = json.dumps(v['state'], sort_keys=True)
    by_state.setdefault(key, []).append((k, v))

for n, (key, group) in enumerate(sorted(by_state.items())):
    stem = f'docs_ex_state_{n:02d}'
    files[stem] = {ident(k): question(v, k) for k, v in group}
    states[stem] = json.loads(key)

# A field id is `<query>/<question>`, and each query was a real call.
for k, v in load('field').items():
    stem, _, target = k.partition('/')
    assert target, f'{k}: field ids are <query>/<question>'
    files.setdefault(stem, {})[ident(target)] = question(v, k)

OUT.mkdir(parents=True, exist_ok=True)

# A query file left behind by an earlier build is harvested as though it were
# part of this one, which is how a renamed tier got scored twice.
written = {f'{stem}.json' for stem in files}
stale = [p for p in OUT.glob('*.json') if p.name not in written and p.name != 'all-scores.json']

for p in stale:
    p.unlink()

if stale:
    print(f'removed {len(stale)} query file{"" if len(stale) == 1 else "s"} from an earlier build')

for stem, questions in sorted(files.items()):
    assert questions, stem
    query = {'questions': questions}

    if stem in states:
        query = {'state': states[stem], 'questions': questions}

    (OUT / f'{stem}.json').write_text(json.dumps(query, indent=2, ensure_ascii=False) + '\n')

print(f'{len(files)} query files, {sum(len(q) for q in files.values())} questions, in {OUT}, '
      f'{len(states)} of them carrying a state')
