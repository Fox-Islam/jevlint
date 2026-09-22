"""Score `state/answer-absent` against SQuAD 2.0, which somebody else labelled.

The check asks whether the state can answer the question. SQuAD 2.0 is a set of
paragraphs with questions marked answerable or not from that paragraph alone, by
people with no knowledge of this catalogue. It is the only material in this
repository whose label for a state-scoped check comes from outside it.

    python3 corpus/squad.py [--items=40] [--env=.env] [--out=local/squad-scores.json]

The dataset is not committed. It is fetched to local/ on first run.
"""
import json, os, pathlib, random, subprocess, sys, urllib.request
from datetime import datetime, timezone

URL = 'https://rajpurkar.github.io/SQuAD-explorer/dataset/dev-v2.0.json'
CHECK = 'state/answer-absent'
SEED = 20260922

arg = lambda name, default: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{name}=')), default)
items = int(arg('items', '40'))
env_file = arg('env', '.env' if pathlib.Path('.env').is_file() else None)
out_path = pathlib.Path(arg('out', 'local/squad-scores.json'))
work = pathlib.Path('local/squad')
work.mkdir(parents=True, exist_ok=True)

dataset = pathlib.Path('local/squad-dev-v2.0.json')
if not dataset.is_file():
    print(f'fetching {URL}', file=sys.stderr)
    urllib.request.urlretrieve(URL, dataset)

pairs = [(p['context'], q['question'], q['is_impossible'])
         for a in json.loads(dataset.read_text())['data']
         for p in a['paragraphs'] for q in p['qas']]

# Balanced and seeded, so two runs of this script measure the same material.
rng = random.Random(SEED)
answerable = [x for x in pairs if not x[2]]
impossible = [x for x in pairs if x[2]]
sample = rng.sample(answerable, items // 2) + rng.sample(impossible, items - items // 2)
rng.shuffle(sample)

scored, calls, unreachable = [], 0, 0

for n, (context, question, is_impossible) in enumerate(sample):
    path = work / f'{n:03d}.json'
    path.write_text(json.dumps({
        'state': {'passage': context},
        # A Noul, because the check reads the question against the state and the
        # answer shape it asks for is not what is being measured here.
        'questions': {'asked': {'type': 'noul', 'instructions': question}},
    }, indent=2))

    out = subprocess.run(
        ['php', 'php/bin/jevlint', 'check', str(path), f'--only={CHECK}', '--all', '--format=json']
        + ([f'--env-file={env_file}'] if env_file else []),
        capture_output=True, text=True).stdout

    report = json.loads(out)

    if not report['summary'].get('complete', True):
        sys.exit(f'item {n}: the call could not be made. Nothing written.')

    calls += report['summary']['calls']
    reading = next((f['probability'] for f in [*report['findings'], *report['cleared']]
                    if f['check'] == CHECK and 'probability' in f), None)

    if reading is None:
        unreachable += 1
        continue

    scored.append({'impossible': is_impossible, 'reading': reading, 'question': question})
    print(f'  {n:3d} {"unanswerable" if is_impossible else "answerable  "} {reading:.2f}', file=sys.stderr)

out_path.parent.mkdir(exist_ok=True)
out_path.write_text(json.dumps({
    'source': URL,
    'seed': SEED,
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'check': CHECK,
    'calls': calls,
    'scored': scored,
}, indent=2) + '\n')

hit = [s['reading'] for s in scored if s['impossible']]
miss = [s['reading'] for s in scored if not s['impossible']]
mean = lambda xs: sum(xs) / len(xs) if xs else float('nan')
trigger = next(c.get('trigger', 0.7) for c in json.loads(pathlib.Path('checks/catalogue.json').read_text())['checks']
               if c['id'] == CHECK)

print(f'\n{len(scored)} scored, {calls} calls, {unreachable} without a reading')
print(f'trigger {trigger}')
print(f'unanswerable: mean {mean(hit):.2f}, fires {sum(1 for r in hit if r > trigger)}/{len(hit)}')
print(f'answerable:   mean {mean(miss):.2f}, fires {sum(1 for r in miss if r > trigger)}/{len(miss)}')
print(f'separation:   {mean(hit) - mean(miss):+.2f}')
