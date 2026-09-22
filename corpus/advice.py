"""Does acting on a finding improve the answer, or only quiet the check?

Every other measurement here is circular: the self-test shows a check's advice
stops that check firing, which is the check grading its own homework. This asks
what the query answers, against labels this repository did not write.

`choice/no-fallback` says a Choice with no catch-all puts its probability on the
nearest wrong label. decision-v7's `none_absent` rows are exactly that case: the
true answer is none of the offered options, and the option that says so is in the
criteria. Taking it out is the defect; putting it back is the advice.

  none_absent   the answer is none of the options.
                without the catch-all every option is wrong, so the reading on
                the one that wins is confidence in a wrong label.
                with it, the answer is available and can be scored.

  none_present  the answer is among the options, so the catch-all is not needed.
                Running both ways says what the advice costs when the defect it
                names is not there.

    python3 corpus/advice.py [--items=30] [--env=.env] [--out=local/advice-scores.json]
"""
import json, pathlib, random, re, subprocess, sys, sys

# decision-v7 is fetched once by corpus/decision.py and shared. Reading it
# straight gave a traceback naming a path, where what a reader needs is the
# command that puts it there.
def _decision_v7():
    dataset = pathlib.Path('local/decision-v7-test.jsonl')

    if not dataset.is_file():
        sys.exit(f'{dataset} is not there. Run `python3 corpus/decision.py` first; it fetches the dataset.')

    return [json.loads(line) for line in dataset.open()]

from datetime import datetime, timezone

EXPERIMENTS = {
    # The check, the rows it is about, and what removing its advice does.
    'fallback': ('choice/no-fallback', ('none_absent', 'none_present')),
    'descriptions': ('choice/undescribed-options', ('none_present',)),
}
SEED = 20260922

arg = lambda name, default: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{name}=')), default)
experiment = arg('experiment', 'fallback')
CHECK, VARIANTS = EXPERIMENTS[experiment]
items = int(arg('items', '30'))
env_file = arg('env', '.env' if pathlib.Path('.env').is_file() else None)
out_path = pathlib.Path(arg('out', f'local/advice-{experiment}.json'))
work = pathlib.Path('local/advice')
work.mkdir(parents=True, exist_ok=True)
env = [f'--env-file={env_file}'] if env_file else []

rows = _decision_v7()


def answer(query, name):
    """What Jev picks and how strongly, through `probe`, which sends it as written."""
    path = work / name
    path.write_text(json.dumps(query, indent=2))
    report = json.loads(subprocess.run(
        ['php', 'php/bin/jevlint', 'probe', str(path), '--repeats=1', '--format=json'] + env,
        capture_output=True, text=True).stdout)

    if not report['summary'].get('complete', True):
        sys.exit(f'{name}: the call could not be made. Nothing written.')

    question = next(iter(report['questions'].values()))
    won = re.search(r'probability of `(.+)`', question.get('reading') or '')

    return (won.group(1) if won else None), question['baseline']


def fires(query, name):
    """Whether the check this is about fires on the query as given."""
    path = work / name
    path.write_text(json.dumps(query, indent=2))
    report = json.loads(subprocess.run(
        ['php', 'php/bin/jevlint', 'check', str(path), f'--only={CHECK}', '--static-only', '--format=json'] + env,
        capture_output=True, text=True).stdout)

    return any(f['check'] == CHECK for f in report['findings'])


def arms(row):
    """The query with the defect, and the query with the check's advice applied."""
    qid, question = next(iter(row['questions'].items()))
    none_key = row['_meta']['none_key']
    asked = {k: v for k, v in question.items() if k in ('type', 'instructions', 'criteria')}

    if experiment == 'fallback':
        broken = dict(asked, criteria={k: v for k, v in asked['criteria'].items() if k != none_key})
    else:
        # The same labels with their descriptions taken away. Passing a list of
        # labels is the same thing: the SDK turns it into a map of nulls before
        # the request goes out, so the API never receives a list.
        broken = dict(asked, criteria={k: None for k in asked['criteria']})

    return (
        {'state': row['state'], 'questions': {qid: broken}},
        {'state': row['state'], 'questions': {qid: asked}},
        question['label'], none_key,
    )


scored = []
sample = {v: random.Random(SEED).sample([r for r in rows if r['_meta'].get('variant') == v], items)
          for v in VARIANTS}

for variant, chosen in sample.items():
    for n, row in enumerate(chosen):
        broken, fixed, label, none_key = arms(row)
        name = f'{variant}-{n:03d}'
        won_b, p_b = answer(broken, f'{name}-without.json')
        won_f, p_f = answer(fixed, f'{name}-with.json')

        scored.append({
            'variant': variant,
            'id': row['_meta']['id'],
            'label': label,
            'none_key': none_key,
            'fires_without': fires(broken, f'{name}-lint.json'),
            'without': {'won': won_b, 'probability': p_b},
            'with': {'won': won_f, 'probability': p_f},
        })
        print(f'  {name} without {won_b} {p_b}  with {won_f} {p_f}', file=sys.stderr)

out_path.write_text(json.dumps({
    'source': 'decision-v7 test.jsonl',
    'seed': SEED,
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'check': CHECK,
    'scored': scored,
}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs) if xs else float('nan')

for variant in VARIANTS:
    group = [s for s in scored if s['variant'] == variant]

    if not group:
        continue

    right = lambda arm, s: s[arm]['won'] == s['label']
    brier = lambda arm, s: (s[arm]['probability'] - (1.0 if right(arm, s) else 0.0)) ** 2
    print(f'\n{variant}, {len(group)} cases. {CHECK} fires on '
          f"{sum(1 for s in group if s['fires_without'])}/{len(group)} of the undone arm.")

    labels = ('advice undone', 'as the check would have it')

    for arm, what in (('without', labels[0]), ('with', labels[1])):
        hits = sum(1 for s in group if right(arm, s))
        print(f'  {what:20s} picks the labelled answer {hits}/{len(group)}, '
              f'mean reading on what it picked {mean([s[arm]["probability"] for s in group]):.2f}, '
              f'Brier {mean([brier(arm, s) for s in group]):.3f}')
