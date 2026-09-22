"""What three wording defects cost, and whether their advice gets it back.

The same design as `rewrite.py`, on material the model does not already answer
perfectly: decision-v7's contrastive rows, where a policy and a case sit in the
state and the model gets about four in five right. Two question wordings, many
states, so the only thing changing between arms is the defect.

The rewriting is done blind through mandos: the panel that injects each defect
never sees the labels, and the panel that repairs it never sees the original or
the other defects' versions of the same question. Both are recorded in
`local/wq-arms.json` before anything is scored.

    python3 corpus/wording.py [--items=20] [--env=.env]
"""
import json, pathlib, re, subprocess, sys

# The arms and the sample are the experiment's inputs, not its output, so they
# are shipped. A run picks up a local copy where one exists, which is how a
# rewrite is tried without editing the committed one.
def _input(name):
    local = pathlib.Path('local') / name
    return local if local.is_file() else pathlib.Path('corpus/arms') / name

from datetime import datetime, timezone

CHECKS = {
    'double_negative': 'question/double-negative',
    'negated': 'noul/negated-phrasing',
    'indirection': 'question/indirection',
    'compound': 'question/compound-judgment',
}
arg = lambda name, default: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{name}=')), default)
items = int(arg('items', '20'))
env_file = arg('env', '.env' if pathlib.Path('.env').is_file() else None)
env = [f'--env-file={env_file}'] if env_file else []
work = pathlib.Path('local/wording')
work.mkdir(parents=True, exist_ok=True)

sample = json.loads(_input('wq-sample.json').read_text())['sample'][:items]
arms = json.loads(_input('wq-arms.json').read_text())

# Every arm has to be a rewrite of the row's own question, or the arms measure
# different things. A misaligned run of this experiment reported an effect that
# vanished once the rows lined up.
for row in sample:
    assert row['question'] in arms, row['question']


def run(args):
    return json.loads(subprocess.run(['php', 'php/bin/jevlint', *args, '--format=json'] + env,
                                     capture_output=True, text=True).stdout)


def query(row, instructions):
    return {'state': row['state'], 'questions': {'q': {'type': 'noul', 'instructions': instructions}}}


def ask(row, instructions, name):
    path = work / name
    path.write_text(json.dumps(query(row, instructions), indent=2))
    report = run(['probe', str(path), '--repeats=1'])

    if not report['summary'].get('complete', True):
        sys.exit(f'{name}: the call could not be made. Nothing written.')

    return next(iter(report['questions'].values()))['baseline']


def fires(row, instructions, check, name):
    path = work / name
    path.write_text(json.dumps(query(row, instructions), indent=2))

    return any(f['check'] == check for f in run(['check', str(path), f'--only={check}'])['findings'])


scored = []

for n, row in enumerate(sample):
    variants = arms[row['question']]
    arm = {'original': row['question']}

    for defect in CHECKS:
        arm[defect] = variants[defect]
        arm[f'{defect}_repaired'] = variants[f'{defect}_repaired']

    scored.append({
        'id': row['id'],
        'family': row['family'],
        'label': bool(row['label']),
        'reading': {k: ask(row, v, f'{n:02d}-{k}.json') for k, v in arm.items()},
        'fires': {defect: fires(row, variants[defect], check, f'{n:02d}-{defect}-lint.json')
                  for defect, check in CHECKS.items()},
    })
    print(f"  {n:02d} {scored[-1]['reading']}", file=sys.stderr)

pathlib.Path('local/wording-scores.json').write_text(json.dumps({
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'scored': scored,
}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs)
brier = lambda armed: mean([(s['reading'][armed] - (1.0 if s['label'] else 0.0)) ** 2 for s in scored])
right = lambda armed: sum(1 for s in scored if (s['reading'][armed] > 0.5) == s['label'])

print(f'\n{len(scored)} contrastive cases')
print(f"  {'original':28s} Brier {brier('original'):.3f}  right {right('original')}/{len(scored)}")

for defect, check in CHECKS.items():
    caught = sum(1 for s in scored if s['fires'][defect])
    print(f"  {defect:28s} Brier {brier(defect):.3f}  right {right(defect)}/{len(scored)}  "
          f'{check} fires {caught}/{len(scored)}')
    print(f"  {defect + ', repaired':28s} Brier {brier(defect + '_repaired'):.3f}  "
          f"right {right(defect + '_repaired')}/{len(scored)}")
