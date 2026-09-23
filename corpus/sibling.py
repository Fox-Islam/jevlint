"""What it costs to put what a question needs into another question.

The documentation says questions in one request are independent, and that one
answer does not become context for another. This puts a figure on what that
costs somebody who wrote a query the other way.

decision-v7's contrastive rows carry a `policy` and a `case` in one state, and
the question needs the policy, so the policy can be moved without touching
anything else:

  whole    the state as decision-v7 ships it
  sibling  the policy taken out of the state and put in another question's
           instructions, in the same request
  absent   the policy taken out and put nowhere, which is the floor

A `sibling` arm at the floor is what makes `question/refers-to-sibling` an error:
the question is answered as though the material it names had never been sent.

    python3 corpus/sibling.py [--items=30] [--env=.env] [--out=local/sibling-scores.json]
"""
import json, pathlib, random, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from answers import key, scored as against_label

SEED = 20260923
ARMS = ('whole', 'sibling', 'absent')

arg = lambda name, default: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{name}=')), default)
items = int(arg('items', '30'))
out_path = pathlib.Path(arg('out', 'local/sibling-scores.json'))
api_key = key(arg('env', '.env' if pathlib.Path('.env').is_file() else None))

dataset = pathlib.Path('local/decision-v7-test.jsonl')

if not dataset.is_file():
    sys.exit(f'{dataset} is not there. Run `python3 corpus/decision.py` first; it fetches the dataset.')

rows = [json.loads(line) for line in dataset.open()]
contrastive = [r for r in rows if r['_meta'].get('source') == 'contrastive' and 'policy' in r.get('state', {})]
sample = random.Random(SEED).sample(contrastive, min(items, len(contrastive)))


def arm(row, which):
    """The request for one arm, as state and questions."""
    qid, question = next(iter(row['questions'].items()))
    asked = {k: v for k, v in question.items() if k in ('type', 'instructions', 'criteria') and v is not None}
    state = {k: v for k, v in row['state'].items() if k != 'policy' or which == 'whole'}
    questions = {}

    if which == 'sibling':
        # The policy travels as another question's instructions. The sibling is
        # answerable on its own, so the request is one a caller might write.
        questions['policy'] = {
            'type': 'noul',
            'instructions': f"{row['state']['policy']} Is that policy stated in plain terms?",
        }

    return state, questions | {qid: asked}, qid, question['label']


def send(job):
    row, which = job
    state, questions, qid, label = arm(row, which)
    body = json.dumps({'state': state, 'model': 'jev-latest', 'questions': questions}).encode()
    call = urllib.request.Request(
        'https://api.typesafe.ai/v1/systemone', data=body, headers={
            'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json',
            'User-Agent': 'jevlint-corpus/1.0'})

    with urllib.request.urlopen(call, timeout=120) as response:
        answers = json.load(response)['answers']

    got = against_label(answers[qid], label)
    print('.', end='', file=sys.stderr, flush=True)

    return {
        'id': row['_meta']['family_id'], 'family': row['_meta']['family'], 'arm': which,
        'label': label, 'on_label': got[0] if got else None, 'right': got[1] if got else None,
    }


jobs = [(row, which) for row in sample for which in ARMS]
print(f'{len(jobs)} calls', file=sys.stderr)

with ThreadPoolExecutor(max_workers=4) as pool:
    scored = list(pool.map(send, jobs))

print('', file=sys.stderr)

out_path.write_text(json.dumps({
    'source': 'decision-v7 test.jsonl, contrastive rows',
    'seed': SEED,
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'items': len(sample),
    'scored': scored,
}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs) if xs else float('nan')

for which in ARMS:
    group = [s for s in scored if s['arm'] == which and s['on_label'] is not None]
    print(f'{which:8s} answers the label {sum(1 for s in group if s["right"]):2d}/{len(group)}, '
          f'mean on label {mean([s["on_label"] for s in group]):.3f}, '
          f'Brier {mean([(1.0 - s["on_label"]) ** 2 for s in group]):.3f}')
