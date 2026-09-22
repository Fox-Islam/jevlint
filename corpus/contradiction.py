"""What inverted criteria cost, and whether swapping them back recovers it.

`question/criteria-contradiction` is `error` severity and says material that
satisfies the instruction would be placed the opposite way by the criteria.
decision-v7's imdb rows ask "Is this movie review positive?" with criteria that
agree with it, so swapping the two descriptions puts the defect in and nothing
else changes. The label follows the instruction, which is the question as asked.

The repair, written blind from the defective question and the check's own
suggestion, restores the criteria, so the third arm also measures this run's
repeat noise.

    python3 corpus/contradiction.py [--env=.env]
"""
import json, pathlib, subprocess, sys

# The arms and the sample are the experiment's inputs, not its output, so they
# are shipped. A run picks up a local copy where one exists, which is how a
# rewrite is tried without editing the committed one.
def _input(name):
    local = pathlib.Path('local') / name
    return local if local.is_file() else pathlib.Path('corpus/arms') / name

from datetime import datetime, timezone

CHECK = 'question/criteria-contradiction'
arg = lambda n, d: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{n}=')), d)
env_file = arg('env', '.env' if pathlib.Path('.env').is_file() else None)
env = [f'--env-file={env_file}'] if env_file else []
work = pathlib.Path('local/contradiction')
work.mkdir(parents=True, exist_ok=True)

sample = json.loads(_input('cc-sample.json').read_text())['sample']
# What the panel returned, blind to the original and to the labels.
REPAIRED = {'true': 'The reviewer liked the film overall', 'false': 'The reviewer disliked the film overall'}


def run(args):
    return json.loads(subprocess.run(['php', 'php/bin/jevlint', *args, '--format=json'] + env,
                                     capture_output=True, text=True).stdout)


def query(row, criteria):
    return {'state': row['state'],
            'questions': {'q': {'type': 'noul', 'instructions': row['instructions'], 'criteria': criteria}}}


def ask(row, criteria, name):
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
    arms = {
        'agreeing': row['criteria'],
        'inverted': {'true': row['criteria']['false'], 'false': row['criteria']['true']},
        'swapped_back': REPAIRED,
    }
    scored.append({
        'id': row['id'],
        'label': bool(row['label']),
        'reading': {k: ask(row, v, f'{n:02d}-{k}.json') for k, v in arms.items()},
        'fires': {k: fires(row, v, f'{n:02d}-{k}-lint.json') for k, v in arms.items()},
    })
    print(f"  {n:02d} label {row['label']} {scored[-1]['reading']}", file=sys.stderr)

pathlib.Path('local/contradiction-scores.json').write_text(json.dumps({
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'), 'check': CHECK, 'scored': scored}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs)
print(f'\n{len(scored)} imdb rows')

for arm in scored[0]['reading']:
    brier = mean([(s['reading'][arm] - (1.0 if s['label'] else 0.0)) ** 2 for s in scored])
    right = sum(1 for s in scored if (s['reading'][arm] > 0.5) == s['label'])
    print(f"  {arm:14s} Brier {brier:.3f}  answers right {right}/{len(scored)}  "
          f"{CHECK} fires {sum(1 for s in scored if s['fires'][arm])}/{len(scored)}")
