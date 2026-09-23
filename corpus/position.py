"""Does where the catch-all is listed change what a Choice answers?

`choice/no-fallback` says to add `other`, and its suggestion writes it at the
end. A published account of the model reports a position bias, the correct
option picked 16 of 16 times listed last against 12 of 16 first. If that holds,
an appended catch-all is a favoured slot rather than a better query, and the
Brier figures `advice.py` produces belong partly to the position.

decision-v7 scatters its catch-all through the option list instead of appending
it, so those figures are not taken from one position. This holds the question,
the state and the options still and moves only the catch-all:

  as_written  where decision-v7 put it
  first       listed before every other option
  last        listed after every other option

Its `none_absent` rows are where the catch-all is the labelled answer, so moving
it is moving the correct option. Its `none_present` rows are where the catch-all
is wrong, so a position that pulls answers onto it shows up as a loss.

    python3 corpus/position.py [--items=24] [--env=.env] [--out=local/position-scores.json]
"""
import json, pathlib, random, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from answers import ask, key

SEED = 20260923
VARIANTS = ('none_absent', 'none_present')

arg = lambda name, default: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{name}=')), default)
items = int(arg('items', '24'))
out_path = pathlib.Path(arg('out', 'local/position-scores.json'))
api_key = key(arg('env', '.env' if pathlib.Path('.env').is_file() else None))

dataset = pathlib.Path('local/decision-v7-test.jsonl')

if not dataset.is_file():
    sys.exit(f'{dataset} is not there. Run `python3 corpus/decision.py` first; it fetches the dataset.')

rows = [json.loads(line) for line in dataset.open()]


def moved(criteria, none_key, where):
    """The same options with the catch-all first, last, or where it was."""
    if where == 'as_written':
        return dict(criteria)

    rest = [(k, v) for k, v in criteria.items() if k != none_key]
    pair = (none_key, criteria[none_key])

    return dict([pair] + rest if where == 'first' else rest + [pair])


def plan():
    """One task per row per arm, with arms that list the options alike sharing a call."""
    tasks, seen = [], {}

    for variant in VARIANTS:
        pool = [r for r in rows if r['_meta'].get('variant') == variant]

        for n, row in enumerate(random.Random(SEED).sample(pool, items)):
            qid, question = next(iter(row['questions'].items()))
            none_key = row['_meta']['none_key']

            for where in ('as_written', 'first', 'last'):
                criteria = moved(question['criteria'], none_key, where)
                # A catch-all decision-v7 already wrote last makes `last` the
                # same request as `as_written`; asking twice buys nothing.
                shape = (row['_meta']['id'], tuple(criteria))
                tasks.append({
                    'variant': variant, 'id': row['_meta']['id'], 'n': n, 'where': where,
                    'qid': qid, 'label': question['label'], 'none_key': none_key,
                    'at': list(criteria).index(none_key) + 1, 'of': len(criteria),
                    'state': row['state'],
                    'question': dict(question, criteria=criteria),
                    'shares': seen.setdefault(shape, len(tasks)),
                })

    return tasks


tasks = plan()
fresh = [t for i, t in enumerate(tasks) if t['shares'] == i]
print(f'{len(tasks)} arms, {len(fresh)} calls', file=sys.stderr)


def run(task):
    answer = ask(api_key, task['state'], task['qid'], task['question'])
    print('.', end='', file=sys.stderr, flush=True)

    return task['shares'], answer


with ThreadPoolExecutor(max_workers=4) as pool:
    answers = dict(pool.map(run, fresh))

print('', file=sys.stderr)

scored = []

for task in tasks:
    answer = answers[task['shares']]
    picked = answer.get('choice')
    scored.append({k: task[k] for k in ('variant', 'id', 'where', 'label', 'at', 'of')} | {
        'picked': picked,
        'right': picked == task['label'],
        'on_label': answer.get('probabilities', {}).get(task['label'], 0.0),
        'on_catch_all': answer.get('probabilities', {}).get(task['none_key'], 0.0),
    })

out_path.write_text(json.dumps({
    'source': 'decision-v7 test.jsonl',
    'seed': SEED,
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'items': items,
    'calls': len(fresh),
    'scored': scored,
}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs) if xs else float('nan')

for variant in VARIANTS:
    group = [s for s in scored if s['variant'] == variant]
    print(f'\n{variant}, {len(group) // 3} cases')

    for where in ('as_written', 'first', 'last'):
        arm = [s for s in group if s['where'] == where]
        print(f'  catch-all {where:10s} picks the label {sum(1 for s in arm if s["right"]):2d}/{len(arm)}, '
              f'mean on label {mean([s["on_label"] for s in arm]):.3f}, '
              f'mean on catch-all {mean([s["on_catch_all"] for s in arm]):.3f}, '
              f'Brier {mean([(1.0 - s["on_label"]) ** 2 for s in arm]):.3f}')
