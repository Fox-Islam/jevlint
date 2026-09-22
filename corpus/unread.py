"""Does `state/irrelevant-field` find a field no question reads?

The corpus has one reading for it, because a state-scoped check needs a state
with named fields and most corpus files carry none. decision-v7's contrastive
rows carry a state of exactly two fields, `policy` and `case`, both of which the
question needs. Adding a third that nothing reads puts the defect in and changes
nothing else.

    python3 corpus/unread.py [--items=20] [--env=.env]
"""
import json, pathlib, random, subprocess, sys, sys

# decision-v7 is fetched once by corpus/decision.py and shared. Reading it
# straight gave a traceback naming a path, where what a reader needs is the
# command that puts it there.
def _decision_v7():
    dataset = pathlib.Path('local/decision-v7-test.jsonl')

    if not dataset.is_file():
        sys.exit(f'{dataset} is not there. Run `python3 corpus/decision.py` first; it fetches the dataset.')

    return [json.loads(line) for line in dataset.open()]

from datetime import datetime, timezone

CHECK = 'state/irrelevant-field'
arg = lambda n, d: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{n}=')), d)
items = int(arg('items', '20'))
env_file = arg('env', '.env' if pathlib.Path('.env').is_file() else None)
env = [f'--env-file={env_file}'] if env_file else []
work = pathlib.Path('local/unread')
work.mkdir(parents=True, exist_ok=True)

# Written before anything was scored. Plausible material, and nothing the
# question asks about.
SPARE = {'warehouse_shift_notes': 'Night shift handover: forklift 3 is back in service, bay 2 still coned off.'}

rows = _decision_v7()
contrastive = [r for r in rows if r['_meta'].get('source') == 'contrastive' and 'policy' in r['state']]
sample = random.Random(20260922).sample(contrastive, items)


def reading(row, state, name):
    path = work / name
    qid, question = next(iter(row['questions'].items()))
    path.write_text(json.dumps({
        'state': state,
        'questions': {qid: {k: v for k, v in question.items() if k in ('type', 'instructions', 'criteria')}},
    }, indent=2))
    report = json.loads(subprocess.run(
        ['php', 'php/bin/jevlint', 'check', str(path), f'--only={CHECK}', '--all', '--format=json'] + env,
        capture_output=True, text=True).stdout)

    if not report['summary'].get('complete', True):
        sys.exit(f'{name}: the call could not be made. Nothing written.')

    # This check is asked once per field and reports the weakest reading, so a
    # fire is what matters rather than which field carried it.
    return (next((f['probability'] for f in [*report['findings'], *report['cleared']]
                  if f['check'] == CHECK and 'probability' in f), None),
            any(f['check'] == CHECK for f in report['findings']))


scored = []

for n, row in enumerate(sample):
    both = reading(row, row['state'], f'{n:02d}-needed.json')
    spare = reading(row, row['state'] | SPARE, f'{n:02d}-spare.json')
    scored.append({'id': row['_meta']['id'], 'needed': both, 'with_spare': spare})
    print(f'  {n:02d} needed {both} with a spare field {spare}', file=sys.stderr)

pathlib.Path('local/unread-scores.json').write_text(json.dumps({
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'), 'check': CHECK,
    'spare_field': SPARE, 'scored': scored}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs) if xs else float('nan')
print(f'\n{len(scored)} states')

for arm, name in (('needed', 'every field needed  '), ('with_spare', 'one field nothing reads')):
    got = [s[arm][0] for s in scored if s[arm][0] is not None]
    print(f"  {name} mean {mean(got):.2f}, fires {sum(1 for s in scored if s[arm][1])}/{len(scored)}")
