"""Does an encoded value in the state cost an answer?

`question/numeric-representation` reads `instructions`, so it fires only when an
encoded value is written into the question text, and the corpus shows it never
firing on real material. The defect it names lives in the state. Before adding a
check that could reach there, this asks whether the defect is real: the same
question over the same fact, written plainly and written encoded.

The answers are arithmetic, so the ground truth is computed here rather than
judged by anyone.

    python3 corpus/encoded.py [--items=12] [--env=.env]
"""
import json, pathlib, random, subprocess, sys
from datetime import datetime, timezone

arg = lambda n, d: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{n}=')), d)
items = int(arg('items', '12'))
env_file = arg('env', '.env' if pathlib.Path('.env').is_file() else None)
env = [f'--env-file={env_file}'] if env_file else []
work = pathlib.Path('local/encoded')
work.mkdir(parents=True, exist_ok=True)

rng = random.Random(20260922)
cases = []

for _ in range(items):
    value = rng.randrange(40, 260)
    limit = rng.randrange(60, 240)
    cases.append({
        'plain': str(value),
        'encoded': hex(value),
        'limit': limit,
        'label': value > limit,
    })


def ask(case, form, name):
    path = work / name
    path.write_text(json.dumps({
        'state': {'reading': case[form]},
        'questions': {'over': {
            'type': 'noul',
            'instructions': f"Is the reading in the state greater than {case['limit']}?",
        }},
    }, indent=2))
    report = json.loads(subprocess.run(
        ['php', 'php/bin/jevlint', 'probe', str(path), '--repeats=1', '--format=json'] + env,
        capture_output=True, text=True).stdout)

    if not report['summary'].get('complete', True):
        sys.exit(f'{name}: the call could not be made. Nothing written.')

    return next(iter(report['questions'].values()))['baseline']


scored = []

for n, case in enumerate(cases):
    scored.append(case | {
        'plain_answer': ask(case, 'plain', f'{n:02d}-plain.json'),
        'encoded_answer': ask(case, 'encoded', f'{n:02d}-encoded.json'),
    })
    print(f"  {n:02d} {case['plain']} vs {case['encoded']} over {case['limit']} "
          f"-> {scored[-1]['plain_answer']} / {scored[-1]['encoded_answer']}", file=sys.stderr)

pathlib.Path('local/encoded-scores.json').write_text(json.dumps({
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'), 'scored': scored}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs)
print(f'\n{len(scored)} readings, each asked plainly and as hex')

for form in ('plain', 'encoded'):
    got = [(s[f'{form}_answer'], s['label']) for s in scored]
    brier = mean([(p - (1.0 if y else 0.0)) ** 2 for p, y in got])
    print(f"  written {form:8s} Brier {brier:.3f}, right {sum(1 for p, y in got if (p > 0.5) == y)}/{len(got)}")
