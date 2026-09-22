"""Measure two things against decision-v7, a corpus with its own ground truth.

`decision-v7` ships states, the questions asked about them, and the answer each
question should get, from ten public datasets plus generated policy cases. Its
contrastive rows carry a `policy` and a `case` in one state, so the policy can be
taken away and put back while everything else holds still.

Two measurements, neither of which this repository could make on its own:

  ablation  `state/answer-absent` claims to find a question the state cannot
            answer. Removing the policy makes exactly that true, so the check
            should read low with it and high without it.

  baseline  What Jev answers, scored against the label with a Brier score. This
            is what a later run has to beat to show that acting on a finding
            improves an answer rather than only quieting a check.

    python3 corpus/decision.py [--items=40] [--env=.env] [--out=local/decision-scores.json]
"""
import json, pathlib, random, subprocess, sys
import urllib.request
from datetime import datetime, timezone

URL = 'https://raw.githubusercontent.com/jaredpalmer/kev/main/evals/v7/decision-v7/test.jsonl'
CHECK = 'state/answer-absent'
SEED = 20260922

arg = lambda name, default: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{name}=')), default)
items = int(arg('items', '40'))
env_file = arg('env', '.env' if pathlib.Path('.env').is_file() else None)
out_path = pathlib.Path(arg('out', 'local/decision-scores.json'))
work = pathlib.Path('local/decision')
work.mkdir(parents=True, exist_ok=True)

dataset = pathlib.Path('local/decision-v7-test.jsonl')
if not dataset.is_file():
    print(f'fetching {URL}', file=sys.stderr)
    urllib.request.urlretrieve(URL, dataset)

rows = [json.loads(line) for line in dataset.open()]
contrastive = [r for r in rows if r['_meta'].get('source') == 'contrastive' and 'policy' in r['state']]
sample = random.Random(SEED).sample(contrastive, min(items, len(contrastive)))

env = [f'--env-file={env_file}'] if env_file else []


def run(args):
    out = subprocess.run(['php', 'php/bin/jevlint', *args, '--format=json'] + env,
                         capture_output=True, text=True).stdout
    return json.loads(out)


def reading(query, name):
    path = work / name
    path.write_text(json.dumps(query, indent=2))
    report = run(['check', str(path), f'--only={CHECK}', '--all'])

    if not report['summary'].get('complete', True):
        sys.exit(f'{name}: the call could not be made. Nothing written.')

    return next((f['probability'] for f in [*report['findings'], *report['cleared']]
                 if f['check'] == CHECK and 'probability' in f), None)


def answer(query, name):
    """What Jev answers, through `probe`, which sends the query as written."""
    path = path = work / name
    path.write_text(json.dumps(query, indent=2))
    report = run(['probe', str(path), '--repeats=1'])

    if not report['summary'].get('complete', True):
        sys.exit(f'{name}: the call could not be made. Nothing written.')

    return next((q['baseline'] for q in report['questions'].values()), None)


scored = []

for n, row in enumerate(sample):
    qid, question = next(iter(row['questions'].items()))
    label = question['label']
    asked = {k: v for k, v in question.items() if k in ('type', 'instructions', 'criteria')}

    withheld = {k: v for k, v in row['state'].items() if k != 'policy'}
    whole = {'state': row['state'], 'questions': {qid: asked}}
    without = {'state': withheld, 'questions': {qid: asked}}

    scored.append({
        'id': row['_meta']['id'],
        'family': row['_meta'].get('family'),
        'label': label,
        'with_policy': reading(whole, f'{n:03d}-with.json'),
        'without_policy': reading(without, f'{n:03d}-without.json'),
        'answer': answer(whole, f'{n:03d}-answer.json'),
    })
    print(f"  {n:3d} {scored[-1]['family']:18s} with {scored[-1]['with_policy']} "
          f"without {scored[-1]['without_policy']} answer {scored[-1]['answer']}", file=sys.stderr)

out_path.parent.mkdir(exist_ok=True)
out_path.write_text(json.dumps({
    'source': URL,
    'seed': SEED,
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'check': CHECK,
    'scored': scored,
}, indent=2) + '\n')

trigger = next(c.get('trigger', 0.7) for c in json.loads(pathlib.Path('checks/catalogue.json').read_text())['checks']
               if c['id'] == CHECK)
mean = lambda xs: sum(xs) / len(xs) if xs else float('nan')
whole_r = [s['with_policy'] for s in scored if s['with_policy'] is not None]
without_r = [s['without_policy'] for s in scored if s['without_policy'] is not None]
answers = [(s['answer'], s['label']) for s in scored if s['answer'] is not None]

print(f'\n{len(scored)} contrastive cases, trigger {trigger}')
print(f'policy in the state:   mean {mean(whole_r):.2f}, fires {sum(1 for r in whole_r if r > trigger)}/{len(whole_r)}')
print(f'policy taken away:     mean {mean(without_r):.2f}, fires {sum(1 for r in without_r if r > trigger)}/{len(without_r)}')
print(f'separation:            {mean(without_r) - mean(whole_r):+.2f}')

if answers:
    brier = mean([(p - (1.0 if y else 0.0)) ** 2 for p, y in answers])
    print(f'\nJev on the question as written: Brier {brier:.3f} over {len(answers)} cases '
          f'(0.25 is a coin flip), accuracy {sum(1 for p, y in answers if (p > 0.5) == bool(y))}/{len(answers)}')
