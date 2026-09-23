"""How often the state-scoped checks fire on states nobody changed.

Every other measurement of a state-scoped check here plants the defect: a line
addressed to the reviewer, a field nothing reads, an edge the question does not
settle. A plant shows a check finds what was put there and says nothing about
what it does to a state that is already right. The corpus cannot answer that
either, because the docs examples that carry a state mostly carry one string,
which leaves `state/irrelevant-field` a single reading.

decision-v7's contrastive rows carry a `policy` and a `case` in one state, the
question asked about them, and the answer it should get. Both fields are needed
to answer, so the state has nothing in it for these checks to find, and a
reading over the trigger is a false positive.

    python3 corpus/fields.py [--items=20] [--env=.env]
"""
import json, pathlib, random, subprocess, sys
from datetime import datetime, timezone

SCOPES = ('state', 'state-field', 'state-once')

arg = lambda n, d: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{n}=')), d)
items = int(arg('items', '20'))
env_file = arg('env', '.env' if pathlib.Path('.env').is_file() else None)
env = [f'--env-file={env_file}'] if env_file else []
work = pathlib.Path('local/fields')
work.mkdir(parents=True, exist_ok=True)

dataset = pathlib.Path('local/decision-v7-test.jsonl')

if not dataset.is_file():
    sys.exit(f'{dataset} is not there. Run `python3 corpus/decision.py` first; it fetches the dataset.')

catalogue = json.loads(pathlib.Path('checks/catalogue.json').read_text())['checks']
watched = {c['id']: c.get('trigger') for c in catalogue
           if c.get('mode') == 'model' and c.get('scope') in SCOPES}

rows = [json.loads(line) for line in dataset.open()]
contrastive = [r for r in rows if r['_meta'].get('source') == 'contrastive' and 'policy' in r['state']]
sample = random.Random(20260922).sample(contrastive, min(items, len(contrastive)))
readings = {check: [] for check in watched}

for n, row in enumerate(sample):
    qid, question = next(iter(row['questions'].items()))
    path = work / f'{n:02d}.json'
    path.write_text(json.dumps({
        'state': row['state'],
        'questions': {qid: {k: v for k, v in question.items() if k in ('type', 'instructions', 'criteria')}},
    }, indent=2))
    report = json.loads(subprocess.run(
        ['php', 'php/bin/jevlint', 'check', str(path), '--all', '--format=json'] + env,
        capture_output=True, text=True).stdout or '{}')

    if not report.get('summary', {}).get('complete', False):
        sys.exit(f'{path}: the call could not be made. Nothing written.')

    for entry in report['findings'] + report['cleared']:
        if entry['check'] in watched and 'probability' in entry:
            readings[entry['check']].append(entry['probability'])

    print(f"  {n:02d} {row['_meta']['id']}", file=sys.stderr)

pathlib.Path('local/fields-scores.json').write_text(json.dumps({
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'states': len(sample), 'readings': readings}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs) if xs else float('nan')
print(f'\n{len(sample)} states with two named fields, both of them needed\n')
print(f'{"check":30s}{"readings":>10s}{"mean":>7s}{"highest":>9s}{"over the trigger":>18s}')

for check, trigger in sorted(watched.items()):
    got = readings[check]

    if not got:
        print(f'{check:30s}{"not asked":>10s}')

        continue

    print(f'{check:30s}{len(got):10d}{mean(got):7.2f}{max(got):9.2f}'
          f'{sum(1 for p in got if p > trigger):12d}/{len(got):<5d}')
