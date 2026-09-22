"""Do the error-severity checks fire where the answers go wrong?

decision-v7's contrastive rows come in four policy families. Three of them turn
on comparing a figure to a threshold and one on comparing two dates, and the
model answers them very differently. This asks the two checks that claim those
defects whether they fire on the questions they are about.

    python3 corpus/families.py [--items=6] [--env=.env]
"""
import json, pathlib, subprocess, sys, collections, random, sys

# decision-v7 is fetched once by corpus/decision.py and shared. Reading it
# straight gave a traceback naming a path, where what a reader needs is the
# command that puts it there.
def _decision_v7():
    dataset = pathlib.Path('local/decision-v7-test.jsonl')

    if not dataset.is_file():
        sys.exit(f'{dataset} is not there. Run `python3 corpus/decision.py` first; it fetches the dataset.')

    return [json.loads(line) for line in dataset.open()]

from datetime import datetime, timezone

CHECKS = ['question/date-comparison', 'question/arithmetic']
arg = lambda n, d: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{n}=')), d)
items = int(arg('items', '6'))
env_file = arg('env', '.env' if pathlib.Path('.env').is_file() else None)
env = [f'--env-file={env_file}'] if env_file else []
work = pathlib.Path('local/families')
work.mkdir(parents=True, exist_ok=True)

rows = _decision_v7()
contrastive = [r for r in rows if r['_meta'].get('source') == 'contrastive' and 'policy' in r['state']]
families = collections.defaultdict(list)

for row in contrastive:
    families[row['_meta']['family']].append(row)

scored = []

for family, group in sorted(families.items()):
    for n, row in enumerate(random.Random(7).sample(group, min(items, len(group)))):
        qid, question = next(iter(row['questions'].items()))
        path = work / f'{family}-{n}.json'
        path.write_text(json.dumps({
            'state': row['state'],
            'questions': {qid: {k: v for k, v in question.items() if k in ('type', 'instructions', 'criteria')}},
        }, indent=2))
        report = json.loads(subprocess.run(
            ['php', 'php/bin/jevlint', 'check', str(path), '--only=' + ','.join(CHECKS), '--all', '--format=json'] + env,
            capture_output=True, text=True).stdout)

        if not report['summary'].get('complete', True):
            sys.exit(f'{family}-{n}: the call could not be made. Nothing written.')

        readings = {f['check']: f['probability'] for f in [*report['findings'], *report['cleared']]
                    if 'probability' in f}
        scored.append({'family': family, 'id': row['_meta']['id'], 'readings': readings,
                       'fired': [f['check'] for f in report['findings'] if f['check'] in CHECKS]})
        print(f'  {family:18} {readings}', file=sys.stderr)

pathlib.Path('local/families-scores.json').write_text(json.dumps({
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'), 'scored': scored}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs) if xs else float('nan')
print(f"\n{'family':20} " + '  '.join(f'{c.split("/")[1]:>18}' for c in CHECKS))

for family in sorted(families):
    group = [s for s in scored if s['family'] == family]
    cells = []

    for check in CHECKS:
        got = [s['readings'][check] for s in group if check in s['readings']]
        fired = sum(1 for s in group if check in s['fired'])
        cells.append(f'{mean(got):.2f}, fires {fired}/{len(group)}')

    print(f'{family:20} ' + '  '.join(f'{c:>18}' for c in cells))
