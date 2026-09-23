"""Does the order of the levels or options change which one a check names?

A check carrying `locate_mode: pick` asks one Choice across the reviewed
question's levels or options and reports the one it picks. A Choice is a Choice,
so if listing order moved answers it would move which element a finding points
at, and a finding would name a different level on a query nobody changed.

The fixtures are the material: each `pick` check's broken example is a question
with the defect in it, in two domains. Each is asked with the elements in the
order the fixture wrote them and again reversed, twice each.

    python3 corpus/locators.py [--repeats=2] [--env=.env]
"""
import json, pathlib, sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from answers import ask, key

arg = lambda name, default: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{name}=')), default)
repeats = int(arg('repeats', '2'))
api_key = key(arg('env', '.env' if pathlib.Path('.env').is_file() else None))

catalogue = {c['id']: c for c in json.loads(pathlib.Path('checks/catalogue.json').read_text())['checks']}
fixtures = json.loads(pathlib.Path('checks/fixtures.json').read_text())['fixtures']


def elements(question):
    """The reviewed question's own levels or options, as the linter lists them."""
    criteria = question.get('criteria')

    if not criteria:
        return {}

    pairs = enumerate(criteria) if isinstance(criteria, list) else criteria.items()

    return {f'level_{k}' if isinstance(criteria, list) else str(k): (v if isinstance(v, str) and v else str(k))
            for k, v in pairs}


def send(job):
    check, domain, order, n, reviewed, options = job
    answer = ask(api_key, reviewed, 'where', {
        'type': 'choice',
        'instructions': catalogue[check]['locate'],
        'criteria': options,
    })
    print('.', end='', file=sys.stderr, flush=True)

    return check, domain, order, answer.get('choice')


jobs = []

for fixture in fixtures:
    check = catalogue[fixture['check']]

    if check.get('locate_mode') != 'pick' or check['scope'] != 'question':
        continue

    reviewed = {k: v for k, v in fixture['broken'].items() if k in ('instructions', 'criteria')}
    options = elements(fixture['broken'])

    if len(options) < 2:
        continue

    domain = fixture.get('domain', 'support')

    for n in range(repeats):
        jobs.append((fixture['check'], domain, 'written', n, reviewed, options))
        jobs.append((fixture['check'], domain, 'reversed', n, reviewed, dict(reversed(list(options.items())))))

print(f'{len(jobs)} calls', file=sys.stderr)

with ThreadPoolExecutor(max_workers=4) as pool:
    got = list(pool.map(send, jobs))

print('', file=sys.stderr)

seen = {}

for check, domain, order, picked in got:
    seen.setdefault((check, domain), {}).setdefault(order, []).append(picked)

agreed = 0

for (check, domain), orders in sorted(seen.items()):
    written = set(orders['written'])
    reversed_ = set(orders['reversed'])
    same = written == reversed_ and len(written) == 1
    agreed += same
    print(f'{check} ({domain})\n  written  {", ".join(orders["written"])}'
          f'\n  reversed {", ".join(orders["reversed"])}   {"same" if same else "DIFFERS"}')

print(f'\n{agreed} of {len(seen)} name the same element either way round.')
