"""Does rewriting a Score's levels as situations put reviews where they belong?

`score/degree-levels` says levels naming degrees of a quality give the model
nothing to match against. decision-v7's sentiment rows are exactly that rubric -
`very negative` to `very positive` - and they carry the level each review belongs
at, from the dataset the review came from.

Three arms: the rubric as the benchmark wrote it, and two rewrites of it made
blind by the panel, which never saw the reviews or the labels.

    python3 corpus/levels.py [--env=.env]
"""
import json, pathlib, subprocess, sys

# The arms and the sample are the experiment's inputs, not its output, so they
# are shipped. A run picks up a local copy where one exists, which is how a
# rewrite is tried without editing the committed one.
def _input(name):
    local = pathlib.Path('local') / name
    return local if local.is_file() else pathlib.Path('corpus/arms') / name

from datetime import datetime, timezone

CHECK = next((a.split('=',1)[1] for a in sys.argv[1:] if a.startswith('--check=')), 'score/degree-levels')
arg = lambda n, d: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{n}=')), d)
env_file = arg('env', '.env' if pathlib.Path('.env').is_file() else None)
env = [f'--env-file={env_file}'] if env_file else []
work = pathlib.Path('local/levels')
work.mkdir(parents=True, exist_ok=True)

sample = json.loads(_input('score-sample.json').read_text())['sample']
rewrites = json.loads(_input('score-arms.json').read_text())

# Each rewrite has to be of the rubric the row carries, and keep its
# length, or the label no longer names the same point on the scale.
for row in sample:
    key = ' | '.join(row['criteria'])
    assert key in rewrites, key

    for levels in rewrites[key].values():
        assert len(levels) == len(row['criteria']), key


def run(args):
    return json.loads(subprocess.run(['php', 'php/bin/jevlint', *args, '--format=json'] + env,
                                     capture_output=True, text=True).stdout)


def query(row, criteria):
    return {'state': row['state'],
            'questions': {'q': {'type': 'score', 'instructions': row['instructions'], 'criteria': criteria}}}


def place(row, criteria, name):
    """Where the review lands, as a position from 0 to 1 over the levels."""
    path = work / name
    path.write_text(json.dumps(query(row, criteria), indent=2))
    report = run(['probe', str(path), '--repeats=1'])

    if not report['summary'].get('complete', True):
        sys.exit(f'{name}: the call could not be made. Nothing written.')

    return next(iter(report['questions'].values()))['baseline']


def fires(row, criteria, name):
    path = work / name
    path.write_text(json.dumps(query(row, criteria), indent=2))

    return any(f['check'] == CHECK for f in run(['check', str(path), f'--only={CHECK}'])['findings'])


scored = []

for n, row in enumerate(sample):
    arms = {'degrees': row['criteria']} | rewrites[' | '.join(row['criteria'])]
    scored.append({
        'id': row['id'],
        'label': row['label'],
        'levels': len(row['criteria']),
        'position': {k: place(row, v, f'{n:02d}-{k}.json') for k, v in arms.items()},
        'fires': {k: fires(row, v, f'{n:02d}-{k}-lint.json') for k, v in arms.items()},
    })
    print(f"  {n:02d} label {row['label']} {scored[-1]['position']}", file=sys.stderr)

pathlib.Path('local/levels-scores.json').write_text(json.dumps({
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'), 'check': CHECK, 'scored': scored}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs)
print(f'\n{len(scored)} sentiment rows, five levels each')

for arm in scored[0]['position']:
    # The label is a level; the reading is a position over the levels.
    target = lambda s: s['label'] / (s['levels'] - 1)
    error = mean([(s['position'][arm] - target(s)) ** 2 for s in scored])
    exact = sum(1 for s in scored if round(s['position'][arm] * (s['levels'] - 1)) == s['label'])
    print(f"  {arm:12s} squared error {error:.3f}  lands on the labelled level {exact}/{len(scored)}  "
          f"{CHECK} fires {sum(1 for s in scored if s['fires'][arm])}/{len(scored)}")
