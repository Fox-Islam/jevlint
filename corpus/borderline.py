"""A borderline case in the state that the question does not decide.

"Does the text contain hello?" is a fine question until the state holds "not
hello", where the thing asked about is mentioned and negated at once and the
query settles neither reading. A check reading only `instructions` cannot find
that, so `question/unsettled-case` reads the question together with the state.

It reads the criteria too, which `scope: state` shows it.

There is no gold negative, so the edge is planted in material somebody else
wrote, the way `planted.py` plants an injection. Each item is one boolq
paragraph with its own sentence about a name taken out and one carrier sentence
put back, so the arms differ in that sentence and in nothing else:

    plain          the name is there and asserted              should not fire
    absent         the name is not there at all                should not fire
    decoy          the name is there, something else negated   should not fire
    negated        the name is there and negated               should fire
    hypothetical   the name is there and conditional           should fire
    negated+named  the same state, criteria naming the edge    should not fire

`decoy` separates the check from a search for the word `not`. `negated+named`
separates it from a search for the state's shape: the edge is there and the
query settles it, so a check reading the query goes quiet and a check
reading only the state does not.

The docs examples that carry a state are run last. Nobody planted anything into
those, so each firing is read by hand.

    python3 corpus/borderline.py [--items=12] [--env=.env]
"""
import json, pathlib, random, re, subprocess, sys
from datetime import datetime, timezone

CHECK = 'question/unsettled-case'

arg = lambda n, d: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{n}=')), d)
items = int(arg('items', '12'))
env_file = arg('env', '.env' if pathlib.Path('.env').is_file() else None)
env = [f'--env-file={env_file}'] if env_file else []

work = pathlib.Path('local/borderline')
work.mkdir(parents=True, exist_ok=True)


def ask(name, query):
    """One reading, through the linter that would run this check."""
    path = work / f'{name}.json'
    path.write_text(json.dumps(query, indent=2))
    run = subprocess.run(
        ['php', 'php/bin/jevlint', 'check', str(path), f'--only={CHECK}', '--all', '--format=json'] + env,
        capture_output=True, text=True)
    report = json.loads(run.stdout or '{}')

    if not report.get('summary', {}).get('complete', False):
        sys.exit(f'{path}: the call could not be made. Nothing written.\n{run.stdout}\n{run.stderr}')

    for row in report.get('findings', []) + report.get('cleared', []):
        if row['check'] == CHECK:
            return row.get('probability')

    return None


def paragraphs():
    """boolq passages, which are Wikipedia prose somebody else wrote."""
    dataset = pathlib.Path('local/decision-v7-test.jsonl')

    if not dataset.is_file():
        sys.exit(f'{dataset} is not there. Run `python3 corpus/decision.py` first; it fetches the dataset.')

    found = []

    for line in dataset.open():
        row = json.loads(line)

        if row['_meta'].get('source') != 'boolq' or not isinstance(row.get('state'), str):
            continue

        term = pick(row['state'])

        # A paragraph naming Baseball once and baseball twice leaves the
        # `absent` arm holding an edge of its own, which is what is measured.
        if term is not None and term.lower() not in arms(row['state'], term)['absent'].lower():
            found.append((row['_meta']['id'], row['state'], term))

    return found


def pick(text):
    """A name the paragraph uses once, so taking it out is unambiguous.

    Capitalised mid-sentence, so a word capitalised because a sentence starts
    with it is not read as a name, and not an adverb or a participle, which read
    as nonsense in the carrier sentence below.
    """
    counts = {}

    for word in re.findall(r'(?<=[a-z,] )([A-Z][a-z]{4,})\b', text):
        counts[word] = counts.get(word, 0) + 1

    once = [w for w, n in counts.items()
            if n == 1 and not w.endswith(('ly', 'ing', 'ed')) and text.count(w) == 1]

    return max(once, key=len) if once else None


def arms(text, term):
    """Every sentence naming the term goes, so one carrier sentence is the only difference."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    rest = ' '.join(s for s in sentences if term not in s)

    return {
        'plain': f'{rest} The report names {term} among those involved.',
        'absent': rest,
        'decoy': f'{rest} The report names {term} among those involved. It does not name who published it.',
        'negated': f'{rest} The report says {term} was not among those involved.',
        'hypothetical': f'{rest} The report asks what would have followed had {term} been among those involved.',
    }


ARMS = ['plain', 'absent', 'decoy', 'negated', 'hypothetical', 'negated+named']
FIRES = {'negated', 'hypothetical'}

pool = paragraphs()
sample = random.Random(20260923).sample(pool, min(items, len(pool)))
scored = []

for n, (row_id, text, term) in enumerate(sample):
    built = arms(text, term)
    asked = f'Does the text mention {term}?'
    edge = {
        'true': f'The text includes the word "{term}", even if it is negated or hypothetical.',
        'false': f'The word "{term}" does not appear anywhere in the text.',
    }

    query = lambda state, criteria: {
        'state': {'text': state},
        'questions': {'mentions': dict({'type': 'noul', 'instructions': asked},
                                       **({'criteria': criteria} if criteria else {}))},
    }

    readings = {arm: ask(f'{n:02d}-{arm}', query(built[arm], None)) for arm in ARMS[:-1]}
    readings['negated+named'] = ask(f'{n:02d}-named', query(built['negated'], edge))

    scored.append({'id': row_id, 'term': term, 'readings': readings})
    print(f'  {n:02d} {term:14s} ' + ' '.join(f'{a}={readings[a]:.2f}' for a in ARMS), file=sys.stderr)

field = []

for path in sorted(pathlib.Path('local/corpus').glob('*.json')):
    query = json.loads(path.read_text())

    if not query.get('state') or not query.get('questions'):
        continue

    for qid in query['questions']:
        field.append({'file': path.name, 'id': qid,
                      'probability': ask(f'field-{path.stem}-{qid}',
                                         {'state': query['state'],
                                          'questions': {qid: query['questions'][qid]}})})

pathlib.Path('local/borderline-scores.json').write_text(json.dumps({
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'check': CHECK, 'planted': scored, 'field': field}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs) if xs else float('nan')
print(f'\n{len(scored)} paragraphs, {len(ARMS)} arms each\n')

for arm in ARMS:
    values = [s['readings'][arm] for s in scored]
    print(f'  {arm:14s} should {"fires " if arm in FIRES else "clears"}  mean {mean(values):.3f}  '
          f'min {min(values):.3f}  max {max(values):.3f}')

positives = [s['readings'][a] for s in scored for a in ARMS if a in FIRES]
negatives = [s['readings'][a] for s in scored for a in ARMS if a not in FIRES]

print(f'\n  span {mean(positives) - mean(negatives):+.3f} between the arms that should fire and the arms that should not')
print(f'  the gap runs from {max(negatives):.2f} to {min(positives):.2f}\n')
print('  trigger   caught    planted false   docs tier')

for bar in (0.30, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70):
    over = [r for r in field if r['probability'] > bar]
    print(f'  {bar:.2f}      {sum(1 for p in positives if p > bar):2d}/{len(positives)}     '
          f'{sum(1 for p in negatives if p > bar):2d}/{len(negatives)}         {len(over):2d}/{len(field)}'
          + (f"  {' '.join(r['id'] for r in over)}" if over else ''))
