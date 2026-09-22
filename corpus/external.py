"""Score two checks against public sets somebody else labelled.

Nine model checks have no labelled defect to catch. For two of them a public
dataset is the defect:

  state/adversarial-content     `deepset/prompt-injections` is text labelled as
                                carrying an instruction aimed at whoever reads
                                it, or not, which is what the check asks.

  query/overlapping-questions   Quora's question pairs are labelled duplicate or
                                not by the people who asked them, which is what
                                the check asks of two questions in one query.

Rows come from the Hugging Face datasets server, so nothing is committed here but
the readings.

    python3 corpus/external.py --check=state/adversarial-content [--items=30] [--env=.env]
"""
import json, pathlib, random, subprocess, sys, urllib.parse, urllib.request
from datetime import datetime, timezone

SETS = {
    'state/adversarial-content': ('deepset/prompt-injections', 'train', 'label'),
    'query/overlapping-questions': ('AlekseyKorshuk/quora-question-pairs', 'train', 'is_duplicate'),
}
arg = lambda n, d: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{n}=')), d)
CHECK = arg('check', 'state/adversarial-content')
dataset, split, label_field = SETS[CHECK]
items = int(arg('items', '30'))
env_file = arg('env', '.env' if pathlib.Path('.env').is_file() else None)
env = [f'--env-file={env_file}'] if env_file else []
work = pathlib.Path('local/external')
work.mkdir(parents=True, exist_ok=True)


def fetch(offset, length=100):
    url = ('https://datasets-server.huggingface.co/rows?dataset=' + urllib.parse.quote(dataset, safe='')
           + f'&config=default&split={split}&offset={offset}&length={length}')

    return [r['row'] for r in json.loads(urllib.request.urlopen(url).read())['rows']]


pool = [row for offset in (0, 100, 200, 300) for row in fetch(offset)]
positive = [r for r in pool if r[label_field] == 1]
negative = [r for r in pool if r[label_field] == 0]
rng = random.Random(20260922)
sample = (rng.sample(positive, min(items // 2, len(positive)))
          + rng.sample(negative, min(items - items // 2, len(negative))))
rng.shuffle(sample)


def query(row):
    if CHECK == 'state/adversarial-content':
        # A question that has to be judged against the material, so the check has
        # both halves in front of it.
        return {'state': {'message': row['text']},
                'questions': {'urgent': {'type': 'noul', 'instructions': 'Does this message need an answer today?'}}}

    return {'questions': {
        'first': {'type': 'noul', 'instructions': row['question1']},
        'second': {'type': 'noul', 'instructions': row['question2']},
    }}


scored = []

for n, row in enumerate(sample):
    path = work / f'{n:03d}.json'
    path.write_text(json.dumps(query(row), indent=2))
    report = json.loads(subprocess.run(
        ['php', 'php/bin/jevlint', 'check', str(path), f'--only={CHECK}', '--all', '--format=json'] + env,
        capture_output=True, text=True).stdout)

    if not report['summary'].get('complete', True):
        sys.exit(f'row {n}: the call could not be made. Nothing written.')

    reading = next((f['probability'] for f in [*report['findings'], *report['cleared']]
                    if f['check'] == CHECK and 'probability' in f), None)
    scored.append({'label': bool(row[label_field]), 'reading': reading,
                   'fired': any(f['check'] == CHECK for f in report['findings'])})
    print(f"  {n:03d} {'defect' if row[label_field] else 'clean '} {reading}", file=sys.stderr)

pathlib.Path(f"local/external-{CHECK.replace('/', '-')}.json").write_text(json.dumps({
    'dataset': dataset, 'check': CHECK,
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'), 'scored': scored}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs) if xs else float('nan')
trigger = next(c.get('trigger', 0.7) for c in json.loads(pathlib.Path('checks/catalogue.json').read_text())['checks']
               if c['id'] == CHECK)
seen = [s for s in scored if s['reading'] is not None]

print(f'\n{CHECK} against {dataset}, {len(seen)} rows with a reading, trigger {trigger}')

for want, name in ((True, 'labelled a defect'), (False, 'labelled clean   ')):
    group = [s for s in seen if s['label'] is want]
    print(f"  {name} mean {mean([s['reading'] for s in group]):.2f}, "
          f"fires {sum(1 for s in group if s['fired'])}/{len(group)}")
