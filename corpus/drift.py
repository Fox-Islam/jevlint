"""How far a re-harvest moved the readings, and which verdicts it changed.

`harvest.py` keeps the file it replaces at `local/scores.previous.json`, so two
runs can be compared. A verdict is the probability against the check's trigger,
so a reading that moves within a band nobody's trigger sits in changes nothing.

Neither run is committed. Comparing them bounds the model's own jitter together
with whatever changed in the catalogue between them; it does not separate the
two, because nothing here sends one catalogue twice.

    python3 corpus/drift.py [previous.json]
"""
import json, pathlib, statistics, sys

cat = json.loads(pathlib.Path('checks/catalogue.json').read_text())
trigger = {c['id']: c.get('trigger', 0.7) for c in cat['checks'] if c['mode'] == 'model'}

now_path = pathlib.Path('corpus/scores.json')
was_path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'local/scores.previous.json')

if not was_path.is_file():
    sys.exit(f'{was_path} is not there. It is written by the next run of corpus/harvest.py.')

read = lambda p: (lambda d: d['scores'] if 'scores' in d else d)(json.loads(p.read_text()))
now, was = read(now_path), read(was_path)

shared = sorted(set(now) & set(was))
deltas, flipped, big = [], [], []

for qid in shared:
    for check, value in now[qid].items():
        if check not in was[qid]:
            continue

        before, after = was[qid][check], value
        deltas.append(abs(after - before))
        edge = trigger.get(check, 0.7)

        if (before > edge) != (after > edge):
            flipped.append((check, qid, before, after, edge))

        if abs(after - before) >= 0.1:
            big.append((abs(after - before), check, qid, before, after))

print(f'{now_path} against {was_path}')
print(f'{len(deltas)} readings shared over {len(shared)} questions')

if not deltas:
    sys.exit('No reading appears in both runs, so there is nothing to compare.')

print(f'median move {statistics.median(deltas):.2f}, largest {max(deltas):.2f}')
print(f'{len(big)} readings moved by 0.1 or more')
print(f'{len(flipped)} verdicts changed:')

for check, qid, before, after, edge in sorted(flipped, key=lambda f: abs(f[2] - f[4]), reverse=True):
    print(f'  {check} on {qid}: {before:.2f} -> {after:.2f}, trigger {edge}, '
          f'{min(abs(before - edge), abs(after - edge)):.2f} from it')

for delta, check, qid, before, after in sorted(big, reverse=True)[:10]:
    print(f'  moved {delta:.2f}: {check} on {qid}, {before:.2f} -> {after:.2f}')
