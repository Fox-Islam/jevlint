"""What an undefined boundary costs: not accuracy, but a steady answer.

`question/undefined-boundary` says a question asking about a line the query never
draws leaves the reader to draw it. The cost is not a wrong answer, because there
is no right one to compare against - it is that the answer does not hold still.
`probe` measures exactly that, and needs no labels.

decision-v7's contrastive states put the line in the policy, so the question as
written has one and the vague rewrite does not. Both arms sit in one query, so
each repeat costs one call for the pair.

    python3 corpus/boundary.py [--items=8] [--repeats=5] [--env=.env]
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

CHECK = 'question/undefined-boundary'
arg = lambda n, d: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{n}=')), d)
items, repeats = int(arg('items', '8')), int(arg('repeats', '5'))
env_file = arg('env', '.env' if pathlib.Path('.env').is_file() else None)
env = [f'--env-file={env_file}'] if env_file else []
work = pathlib.Path('local/boundary')
work.mkdir(parents=True, exist_ok=True)

# Written blind by the panel, from the question alone.
VAGUE = {
    'Is this return request within the policy window?': 'Is this return request timely?',
    'Is the applicant eligible?': 'Is the applicant qualified?',
}

rows = _decision_v7()
pool = [r for r in rows if r['_meta'].get('source') == 'contrastive'
        and next(iter(r['questions'].values()))['instructions'] in VAGUE]
sample = random.Random(20260922).sample(pool, items)
scored = []

for n, row in enumerate(sample):
    asked = next(iter(row['questions'].values()))['instructions']
    path = work / f'{n:02d}.json'
    path.write_text(json.dumps({
        'state': row['state'],
        'questions': {
            'stated': {'type': 'noul', 'instructions': asked},
            'vague': {'type': 'noul', 'instructions': VAGUE[asked]},
        },
    }, indent=2))
    report = json.loads(subprocess.run(
        ['php', 'php/bin/jevlint', 'probe', str(path), f'--repeats={repeats}', '--format=json'] + env,
        capture_output=True, text=True).stdout)

    if not report['summary'].get('complete', True):
        sys.exit(f'{n}: the call could not be made. Nothing written.')

    lint = json.loads(subprocess.run(
        ['php', 'php/bin/jevlint', 'check', str(path), f'--only={CHECK}', '--all', '--no-state', '--format=json'] + env,
        capture_output=True, text=True).stdout)
    fired = {f['target'] for f in lint['findings'] if f['check'] == CHECK}

    scored.append({'id': row['_meta']['id'], 'arms': {
        arm: {'answer': report['questions'][arm]['baseline'],
              'spread': report['questions'][arm]['noise'],
              'fires': arm in fired}
        for arm in ('stated', 'vague')}})
    print(f"  {n:02d} {scored[-1]['arms']}", file=sys.stderr)

pathlib.Path('local/boundary-scores.json').write_text(json.dumps({
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'), 'check': CHECK,
    'vague': VAGUE, 'repeats': repeats, 'scored': scored}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs) if xs else float('nan')
print(f'\n{len(scored)} states, {repeats} repeats each')

for arm, name in (('stated', 'the line is in the policy'), ('vague', 'no line stated        ')):
    spreads = [s['arms'][arm]['spread'] for s in scored if s['arms'][arm]['spread'] is not None]
    print(f"  {name} mean spread over the repeats {mean(spreads):.4f}, "
          f"{CHECK} fires {sum(1 for s in scored if s['arms'][arm]['fires'])}/{len(scored)}")
