"""Does `state/irrelevant-field` find a field no question reads, and what does
that field cost the answer?

The corpus has one reading for the check, because a state-scoped check needs a
state with named fields and most corpus files carry none. decision-v7's
contrastive rows carry a state of exactly two fields, `policy` and `case`, both
of which the question needs. Adding a third that nothing reads puts the defect
in and changes nothing else.

Finding the field is half of it. The other half is whether carrying it costs a
correct answer, which is what decides whether the finding is advice or a
warning. Two things about the spare field could matter and are separated here:
how much of it there is, and whether what it holds could be mistaken for an
answer. The small and large arms are shift notes, unrelated to a policy
question at either size. The fourth arm carries another row's claim, which the
question does not ask about and which reads exactly like the thing it does ask
about. Every answer is scored against the label decision-v7 ships.

    python3 corpus/unread.py [--items=20] [--env=.env]
"""
import json, pathlib, random, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from answers import ask, brier, key, scored

# decision-v7 is fetched once by corpus/decision.py and shared. Reading it
# straight gave a traceback naming a path, where what a reader needs is the
# command that puts it there.
def _decision_v7():
    dataset = pathlib.Path('local/decision-v7-test.jsonl')

    if not dataset.is_file():
        sys.exit(f'{dataset} is not there. Run `python3 corpus/decision.py` first; it fetches the dataset.')

    return [json.loads(line) for line in dataset.open()]

from datetime import datetime, timezone

CHECK = 'state/irrelevant-field'
arg = lambda n, d: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{n}=')), d)
items = int(arg('items', '20'))
env_file = arg('env', '.env' if pathlib.Path('.env').is_file() else None)
env = [f'--env-file={env_file}'] if env_file else []
work = pathlib.Path('local/unread')
work.mkdir(parents=True, exist_ok=True)

# Written before anything was scored. Plausible material, and nothing the
# question asks about.
LINE = 'Night shift handover: forklift 3 is back in service, bay 2 still coned off.'
SPARE = {'warehouse_shift_notes': LINE}

# The same field, at the scale a real one arrives at. A customer routing search
# queries carried about 13,700 characters of unrelated FAQ text beside the
# query, so the large arm is built to that order.
BULK = {'warehouse_shift_notes': '\n'.join(
    f'Shift {n:03d}: {LINE} Bay {n % 7} swept, pallet jack {n % 4} charged, '
    f'{n % 12} totes staged for the morning pick.' for n in range(90))}

API_KEY = key(env_file)

rows = _decision_v7()
contrastive = [r for r in rows if r['_meta'].get('source') == 'contrastive' and 'policy' in r['state']]
sample = random.Random(20260922).sample(contrastive, items)


def reading(row, state, name):
    path = work / name
    qid, question = next(iter(row['questions'].items()))
    path.write_text(json.dumps({
        'state': state,
        'questions': {qid: {k: v for k, v in question.items() if k in ('type', 'instructions', 'criteria')}},
    }, indent=2))
    report = json.loads(subprocess.run(
        ['php', 'php/bin/jevlint', 'check', str(path), f'--only={CHECK}', '--all', '--format=json'] + env,
        capture_output=True, text=True).stdout)

    if not report['summary'].get('complete', True):
        sys.exit(f'{name}: the call could not be made. Nothing written.')

    # This check is asked once per field and reports the weakest reading, so a
    # fire is what matters instead of which field carried it.
    return (next((f['probability'] for f in [*report['findings'], *report['cleared']]
                  if f['check'] == CHECK and 'probability' in f), None),
            any(f['check'] == CHECK for f in report['findings']))


ARMS = ('needed', 'small', 'large', 'confusable')
results = []

for n, row in enumerate(sample):
    qid, question = next(iter(row['questions'].items()))
    label = question['label']
    # Another row's claim, from a case the question was not asked about. The
    # sample is shuffled, so the neighbour is a different family as often as not.
    other = sample[(n + 7) % len(sample)]['state'].get('case', '')
    extras = {'needed': {}, 'small': SPARE, 'large': BULK, 'confusable': {'archived_claim': other}}
    arms = {}

    for arm in ARMS:
        state = row['state'] | extras[arm]
        arms[arm] = {
            'check': reading(row, state, f'{n:02d}-{arm}.json'),
            'answer': scored(ask(API_KEY, state, qid, question), label),
        }

    results.append({'id': row['_meta']['id'], 'type': question['type'], 'label': label, 'arms': arms})
    print(f"  {n:02d} " + '  '.join(
        f"{a} {arms[a]['check'][0]}/{arms[a]['answer'][1] if arms[a]['answer'] else '-'}" for a in ARMS),
        file=sys.stderr)

pathlib.Path('local/unread-scores.json').write_text(json.dumps({
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'), 'check': CHECK,
    'small_field': SPARE, 'large_field_characters': len(BULK['warehouse_shift_notes']),
    'scored': results}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs) if xs else float('nan')
labelled = [r for r in results if r['arms']['needed']['answer'] is not None]
print(f'\n{len(results)} states, {len(labelled)} of them with a label this can score')
print(f"the large field is {len(BULK['warehouse_shift_notes']):,} characters\n")
print(f'{"the state":26s} {"check reads":>11s} {"fires":>7s} {"answer right":>13s} {"Brier":>7s}')

for arm, name in (('needed', 'every field needed'), ('small', 'one spare line'),
                  ('large', 'a large spare field'), ('confusable', 'a spare field like an answer')):
    got = [r['arms'][arm]['check'][0] for r in results if r['arms'][arm]['check'][0] is not None]
    hits = [r['arms'][arm]['answer'] for r in labelled]
    print(f'{name:26s} {mean(got):11.2f} '
          f'{sum(1 for r in results if r["arms"][arm]["check"][1]):4d}/{len(results):<2d} '
          f'{sum(1 for _, ok in hits if ok):9d}/{len(hits):<3d} {brier(hits):7.3f}')
