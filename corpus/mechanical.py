"""Does asking Jev a question code could answer cost an answer?

Before a check tells somebody to take a question out, this asks what leaving it
in costs. Eight questions whose answers follow from the state by a rule - an
equality, a membership, a threshold, a suffix - are asked over states generated
here, so the truth is computed and nobody has to judge it.

A model that answers all of them costs money and determinism and nothing else,
which is advice. A model that misses some costs answers, which is not.

    python3 corpus/mechanical.py [--items=12] [--env=.env] [--out=local/mechanical-scores.json]
"""
import json, pathlib, random, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from answers import key

SEED = 20260923
arg = lambda n, d: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{n}=')), d)
items = int(arg('items', '12'))
out_path = pathlib.Path(arg('out', 'local/mechanical-scores.json'))
api_key = key(arg('env', '.env' if pathlib.Path('.env').is_file() else None))

STATUSES = ['shipped', 'cancelled', 'awaiting_payment', 'delivered', 'refunded']
COUNTRIES = ['GB', 'IE', 'FR', 'DE', 'US', 'NL']
TAGS = ['urgent', 'gift', 'fragile', 'bulk', 'reshipped']
DOMAINS = ['acme.com', 'example.org', 'northwind.co.uk']
BODIES = [
    'The parcel turned up with a dent in one corner and I would like this sorted.',
    'Please cancel and issue a refund to the original card.',
    'Could you confirm when this is due to arrive?',
    'The item is not what the listing described at all.',
]

# Eight questions and the rule each one follows, so the answer is computed from
# the state rather than judged against it.
RULES = {
    'equality': (
        'Is the order\'s `status` field exactly `shipped`?',
        lambda s: s['order']['status'] == 'shipped'),
    'membership': (
        'Is the order\'s `country` field one of GB, IE or FR?',
        lambda s: s['order']['country'] in ('GB', 'IE', 'FR')),
    'threshold': (
        'Is the order\'s `total_pence` field greater than 10000?',
        lambda s: s['order']['total_pence'] > 10000),
    'list_holds': (
        'Do the order\'s `tags` include `urgent`?',
        lambda s: 'urgent' in s['order']['tags']),
    'emptiness': (
        'Is the customer\'s `phone` field empty?',
        lambda s: s['customer']['phone'] == ''),
    'suffix': (
        'Does the customer\'s `email` field end in `@acme.com`?',
        lambda s: s['customer']['email'].endswith('@acme.com')),
    'case': (
        'Is the customer\'s `email` field written in lower case throughout?',
        lambda s: s['customer']['email'] == s['customer']['email'].lower()),
    'literal': (
        'Does the message `body` contain the letters `refund`, as they are written here?',
        lambda s: 'refund' in s['message']['body']),
}


def state(rng):
    email = f"{rng.choice(['sam', 'Alex', 'jo', 'Robin'])}@{rng.choice(DOMAINS)}"

    return {
        'order': {
            'status': rng.choice(STATUSES),
            'total_pence': rng.choice([450, 2999, 10000, 14250, 88000]),
            'country': rng.choice(COUNTRIES),
            'tags': rng.sample(TAGS, rng.randint(1, 3)),
        },
        'customer': {'email': email, 'phone': rng.choice(['', '07700 900123'])},
        'message': {'body': rng.choice(BODIES)},
    }


def send(job):
    n, material = job
    body = json.dumps({
        'state': material,
        'model': 'jev-latest',
        'questions': {name: {'type': 'noul', 'instructions': line} for name, (line, _) in RULES.items()},
    }).encode()
    call = urllib.request.Request(
        'https://api.typesafe.ai/v1/systemone', data=body, headers={
            'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json',
            'User-Agent': 'jevlint-corpus/1.0'})

    with urllib.request.urlopen(call, timeout=120) as response:
        answers = json.load(response)['answers']

    print('.', end='', file=sys.stderr, flush=True)

    return [{
        'state': n, 'rule': name, 'truth': rule(material),
        'noul': answers[name]['noul'], 'said': answers[name]['noul'] > 0.5,
    } for name, (_, rule) in RULES.items()]


rng = random.Random(SEED)
jobs = [(n, state(rng)) for n in range(items)]
print(f'{len(jobs)} calls, {len(jobs) * len(RULES)} answers', file=sys.stderr)

with ThreadPoolExecutor(max_workers=4) as pool:
    scored = [row for batch in pool.map(send, jobs) for row in batch]

print('', file=sys.stderr)

out_path.write_text(json.dumps({
    'source': 'states generated here, answers computed',
    'seed': SEED, 'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'scored': scored,
}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs) if xs else float('nan')

for name in RULES:
    group = [s for s in scored if s['rule'] == name]
    right = [s for s in group if s['said'] == s['truth']]
    confident = [s for s in group if s['noul'] > 0.9 or s['noul'] < 0.1]
    print(f'{name:12s} correct {len(right):2d}/{len(group)}, '
          f'{len(confident)} of them read past 0.9 either way, '
          f'mean on the true answer {mean([s["noul"] if s["truth"] else 1 - s["noul"] for s in group]):.2f}')

right = [s for s in scored if s['said'] == s['truth']]
print(f'\nover all rules: {len(right)}/{len(scored)}, '
      f'Brier {mean([(s["noul"] - (1.0 if s["truth"] else 0.0)) ** 2 for s in scored]):.3f}')
