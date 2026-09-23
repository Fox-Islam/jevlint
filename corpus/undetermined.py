"""How the checks read a Choice over an outcome the material cannot settle.

`jev-does-not-play-dice` asked Jev to name the result of a hidden fair draw and
recorded what came back: a Choice putting a mean 0.83 on the face it picked,
against a chance of 0.17, with accuracy at chance. Its requests are the only
material anywhere with that defect deliberately in it, so they are what
`choice/undetermined-outcome` is measured against.

Three arms over the same states:

  undetermined  the wording `choice/undetermined-outcome` asks
  absent        both wordings of `state/answer-absent`, the nearest check, to
                show that no trigger on it reaches this material

Negatives come from the corpus, so they are questions somebody else wrote: every
Choice question in the docs tier that carries a state, plus the clean example
this repository ships. Two positives are written here, for outcomes that are not
draws, because the recorded ones are all draws.

    python3 corpus/undetermined.py [--env=.env] [--out=local/undetermined-scores.json]
"""
import json, pathlib, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from answers import ask, key

URL = 'https://raw.githubusercontent.com/KantaHayashiAI/jev-does-not-play-dice/main/data/requests/dice.jsonl'

arg = lambda name, default: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{name}=')), default)
out_path = pathlib.Path(arg('out', 'local/undetermined-scores.json'))
api_key = key(arg('env', '.env' if pathlib.Path('.env').is_file() else None))

recorded = pathlib.Path('local/jev-dice-requests.jsonl')

if not recorded.is_file():
    recorded.parent.mkdir(parents=True, exist_ok=True)
    print(f'fetching {URL}', file=sys.stderr)
    urllib.request.urlretrieve(URL, recorded)

catalogue = json.loads(pathlib.Path('checks/catalogue.json').read_text())
wordings = {c['id']: c.get('questions') or [c['question']]
            for c in catalogue['checks']
            if c['id'] in ('choice/undetermined-outcome', 'state/answer-absent')}

# One request per group, not all 1000: the groups differ in what is drawn, and
# the repeats within a group differ only in the wording of the scenario.
draws = {}

for line in recorded.open():
    row = json.loads(line)
    draws.setdefault(row['group'], row['request'])

WRITTEN = {
    'written/parcel-arrival': {
        'state': 'Parcel 88213 left the Leeds depot at 18:40 on Tuesday. The van is on a route with nine '
                 'other drops. No delivery attempt has been recorded.',
        'questions': {'answer': {
            'type': 'choice',
            'instructions': 'Which of these will happen to the parcel?',
            'criteria': {'delivered': 'It is delivered on the first attempt',
                         'carded': 'Nobody is in and a card is left',
                         'refused': 'The recipient refuses it',
                         'other': 'Anything the other options do not cover'}}}},
    'written/ticket-outcome': {
        'state': 'Ticket 4471, opened this morning: "The export button does nothing." '
                 'No engineer has picked it up yet.',
        'questions': {'answer': {
            'type': 'choice',
            'instructions': 'Which team will end up closing this ticket?',
            'criteria': {'support': 'Support closes it without escalating',
                         'engineering': 'Engineering closes it after a fix',
                         'billing': 'Billing closes it',
                         'other': 'Anything the other options do not cover'}}}},
}


def cases():
    """Every case, as (name, positive, question, state)."""
    for group, request in sorted(draws.items()):
        yield f'draw/{group}', True, request['questions']['answer'], request['state']

    for name, request in sorted(WRITTEN.items()):
        yield name, True, request['questions']['answer'], request['state']

    # The corpus files carry the docs tier's own queries. A Choice question in
    # one of them is a negative: somebody wrote it to be answered.
    for path in sorted(pathlib.Path('local/corpus').glob('docs_ex_state_*.json')):
        query = json.loads(path.read_text())

        for qid, question in query['questions'].items():
            if question.get('type') == 'choice':
                yield f'{path.stem}/{qid}', False, question, query.get('state', '')

    clean = json.loads(pathlib.Path('examples/support-triage.json').read_text())
    yield 'examples/support-triage', False, clean['questions']['category'], clean['state']


def send(job):
    name, positive, question, state, check, index = job
    asked = {k: v for k, v in question.items() if k in ('type', 'instructions', 'criteria')}
    shown = json.dumps({'question': asked, 'state': state}, ensure_ascii=False)
    answer = ask(api_key, shown, 'reading', wordings[check][index])
    print('.', end='', file=sys.stderr, flush=True)

    return {'case': name, 'positive': positive, 'check': check, 'wording': index, 'reading': answer['noul']}


jobs = [(name, positive, question, state, check, index)
        for name, positive, question, state in cases()
        for check, asked in wordings.items()
        for index in range(len(asked))]

if not pathlib.Path('local/corpus').is_dir():
    sys.exit('local/corpus is not there. Run `python3 corpus/build.py` first.')

print(f'{len(jobs)} calls', file=sys.stderr)

with ThreadPoolExecutor(max_workers=4) as pool:
    scored = list(pool.map(send, jobs))

print('', file=sys.stderr)

out_path.write_text(json.dumps({
    'source': 'jev-does-not-play-dice data/requests/dice.jsonl, the corpus docs tier, and two cases written here',
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'scored': scored,
}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs) if xs else float('nan')

for check in wordings:
    by_case = {}

    for s in scored:
        if s['check'] == check:
            by_case.setdefault((s['case'], s['positive']), []).append(s['reading'])

    readings = {c: mean(v) for c, v in by_case.items()}
    positives = [v for (_, p), v in readings.items() if p]
    negatives = [v for (_, p), v in readings.items() if not p]

    print(f'{check}')
    print(f'  {len(positives)} undetermined outcomes, {min(positives):.2f} to {max(positives):.2f}')
    print(f'  {len(negatives)} the material settles,  {min(negatives):.2f} to {max(negatives):.2f}')
    band = min(positives) - max(negatives)
    print(f'  floor {min(positives):.2f} against ceiling {max(negatives):.2f}, '
          f'{f"a band of {band:.2f}" if band > 0 else "they overlap"}')
