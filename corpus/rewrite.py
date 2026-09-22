"""Does a wording defect cost an answer, and does the advice get it back?

`choice/no-fallback` could be tested because its advice is a patch. A wording
check's advice is prose, so applying it means somebody rewrites the question, and
whoever rewrites it decides what the experiment measures. Here the rewriting is
done by a panel of models through mandos, blind: the one that injects the defect
never sees the labels, and the one that repairs it never sees the original.

Three arms over the same boolq rows, scored against decision-v7's labels:

  original   the question as the benchmark wrote it
  injected   the same question carrying a double negative, which the check fires on
  repaired   the injected question with the check's suggestion applied, blind

    python3 corpus/rewrite.py [--env=.env]

`local/dn-sample.json` holds the rows and `local/dn-arms.json` the two rewrites,
both recorded before any of this was scored.
"""
import json, pathlib, re, subprocess, sys

# The arms and the sample are the experiment's inputs, not its output, so they
# are shipped. A run picks up a local copy where one exists, which is how a
# rewrite is tried without editing the committed one.
def _input(name):
    local = pathlib.Path('local') / name
    return local if local.is_file() else pathlib.Path('corpus/arms') / name

from datetime import datetime, timezone

CHECK = 'question/double-negative'
arg = lambda name, default: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{name}=')), default)
env_file = arg('env', '.env' if pathlib.Path('.env').is_file() else None)
env = [f'--env-file={env_file}'] if env_file else []
work = pathlib.Path('local/rewrite')
work.mkdir(parents=True, exist_ok=True)

sample = json.loads(_input('dn-sample.json').read_text())['sample']
arms = json.loads(_input('dn-arms.json').read_text())
assert len(sample) == len(arms['injected']) == len(arms['repaired']) == len(arms['repaired_grok'])

# The injected question has to be the sample's question, or the arms are measuring
# different things. This caught a run whose last six rows were another question set.
words = lambda text: {w for w in re.findall(r'[a-z]+', text.lower()) if len(w) > 3}

for row, injected in zip(sample, arms['injected']):
    assert words(row['question']) <= words(injected), row['id']


def run(args):
    return json.loads(subprocess.run(['php', 'php/bin/jevlint', *args, '--format=json'] + env,
                                     capture_output=True, text=True).stdout)


def ask(state, instructions, name):
    path = work / name
    path.write_text(json.dumps({'state': state, 'questions': {'q': {'type': 'noul', 'instructions': instructions}}}))
    report = run(['probe', str(path), '--repeats=1'])

    if not report['summary'].get('complete', True):
        sys.exit(f'{name}: the call could not be made. Nothing written.')

    return next(iter(report['questions'].values()))['baseline']


def fires(state, instructions, name):
    path = work / name
    path.write_text(json.dumps({'state': state, 'questions': {'q': {'type': 'noul', 'instructions': instructions}}}))

    return any(f['check'] == CHECK for f in run(['check', str(path), f'--only={CHECK}'])['findings'])


scored = []

for n, row in enumerate(sample):
    arm = {
        'original': row['question'],
        'injected': arms['injected'][n],
        'injected_hard': arms['injected_hard'][n],
        'repaired': arms['repaired'][n],
        'repaired_grok': arms['repaired_grok'][n],
    }
    scored.append({
        'id': row['id'],
        'label': bool(row['label']),
        'fires': {k: fires(row['state'], v, f'{n:02d}-{k}-lint.json') for k, v in arm.items()},
        'reading': {k: ask(row['state'], v, f'{n:02d}-{k}.json') for k, v in arm.items()},
        'questions': arm,
    })
    print(f"  {n:02d} {scored[-1]['reading']} fires {scored[-1]['fires']}", file=sys.stderr)

pathlib.Path('local/rewrite-scores.json').write_text(json.dumps({
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'check': CHECK,
    'scored': scored,
}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs)
print(f'\n{len(scored)} boolq cases')

for armed in ('original', 'injected', 'injected_hard', 'repaired', 'repaired_grok'):
    brier = mean([(s['reading'][armed] - (1.0 if s['label'] else 0.0)) ** 2 for s in scored])
    right = sum(1 for s in scored if (s['reading'][armed] > 0.5) == s['label'])
    print(f'  {armed:9s} Brier {brier:.3f}  answers right {right}/{len(scored)}  '
          f"check fires {sum(1 for s in scored if s['fires'][armed])}/{len(scored)}")
