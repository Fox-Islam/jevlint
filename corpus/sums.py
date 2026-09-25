"""Where Jev's arithmetic falls apart, and whether `question/arithmetic`'s `cleared_by` stops short of it.

Every item is a sum generated here, so the answer is computed and nobody has to
judge it. Each operation and operand size is asked three ways:

  choice  "What is 312 + 589?", over the answer and two near misses
  true    "Is 312 + 589 equal to 901?"
  false   the same claim with a near miss, differing in the second digit

The clearing question is then asked about the "What is ...?" form of each item,
and a second set asks single-digit claims in the negated form "Is the value of
3 + 2 different from 5?", which the jevlint-tests benchmark
(https://github.com/nunezb/jevlint-tests) sends.

    python3 corpus/sums.py [--items=6] [--env=.env] [--out=local/sums-scores.json]
"""
import json, pathlib, random, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from fractions import Fraction

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from answers import ask, key

SEED = 20260925
arg = lambda name, default: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{name}=')), default)
items = int(arg('items', '6'))
out_path = pathlib.Path(arg('out', 'local/sums-scores.json'))
api_key = key(arg('env', '.env' if pathlib.Path('.env').is_file() else None))

check = next(c for c in json.loads(pathlib.Path('checks/catalogue.json').read_text())['checks']
             if c['id'] == 'question/arithmetic')
CLEARING = check['cleared_by']['question']
STATE = 'Work out the value asked for.'
rng = random.Random(SEED)

CELLS = [(op, digits) for op in ('+', '-', '×', '÷') for digits in (1, 2, 3, 4)] \
    + [(op, digits) for op in ('fraction', 'percent', 'two-step') for digits in (1, 2)]


def number(digits):
    return rng.randint(10 ** (digits - 1) if digits > 1 else 1, 10 ** digits - 1)


def near(value):
    """A miss in the second digit, so it cannot be told apart by magnitude or by the last digit alone."""
    return value + rng.choice([-1, 1]) * 10 ** max(0, len(str(abs(value))) - 2)


def item(op, digits):
    """The expression, its value, and two near misses, all as text."""
    if op == 'fraction':
        a, b, c, d = number(digits), number(digits) + 1, number(digits), number(digits) + 1
        total = Fraction(a, b) + Fraction(c, d)
        n, m = total.numerator, total.denominator

        return f'{a}/{b} + {c}/{d}', f'{n}/{m}', [f'{n + 1}/{m}', f'{n + 2}/{m}']

    if op == 'percent':
        share = rng.choice([5, 10, 15, 20, 25, 30, 40, 50, 75])
        base = number(digits) * 4
        value = share * base // 100 if share * base % 100 == 0 else share * base / 100
        step = 1 if digits == 1 else 10

        return f'{share}% of {base}', f'{value:g}', [f'{value + step:g}', f'{value + 2 * step:g}']

    if op == '+':
        a, b = number(digits), number(digits)
        expression, value = f'{a} + {b}', a + b
    elif op == '-':
        a, b = sorted([number(digits), number(digits)], reverse=True)
        expression, value = f'{a} - {b}', a - b
    elif op == '×':
        a, b = number(digits), number(digits)
        expression, value = f'{a} × {b}', a * b
    elif op == '÷':
        b, value = number(digits), number(digits)
        expression = f'{b * value} ÷ {b}'
    else:
        a, b, c = number(digits), number(digits), number(digits)
        expression, value = f'{a} + {b} × {c}', a + b * c

    first = near(value)

    return expression, str(value), [str(first), str(first + (first - value))]


jobs = []

for op, digits in CELLS:
    for index in range(items):
        expression, value, misses = item(op, digits)
        options = [value, *misses]
        rng.shuffle(options)
        cell = {'op': op, 'digits': digits, 'item': index, 'expression': expression}
        jobs.append({**cell, 'form': 'choice', 'value': value, 'options': options})
        jobs.append({**cell, 'form': 'true', 'claimed': value, 'holds': True})
        jobs.append({**cell, 'form': 'false', 'claimed': misses[0], 'holds': False})
        jobs.append({**cell, 'form': 'clearing'})

for op in ('+', '×'):
    for index in range(10):
        a, b = rng.randint(1, 9), rng.randint(1, 9)
        value = a + b if op == '+' else a * b

        for claimed in (value, value + rng.choice([-1, 1, 2])):
            jobs.append({'op': op, 'digits': 1, 'item': index, 'form': 'negated', 'claimed': str(claimed),
                         'expression': f'{a} {op} {b}', 'holds': claimed != value})


def send(job):
    if job['form'] == 'choice':
        criteria = {f'option_{i}': option for i, option in enumerate(job['options'])}
        answer = ask(api_key, STATE, 'answer', {
            'type': 'choice', 'instructions': f'What is {job["expression"]}?', 'criteria': criteria})
        right = next(label for label, option in criteria.items() if option == job['value'])
        result = {'correct': answer['choice'] == right, 'reading': answer['probabilities'].get(right, 0.0)}
    elif job['form'] == 'clearing':
        shown = json.dumps({'instructions': f'What is {job["expression"]}?'}, ensure_ascii=False)
        result = {'reading': ask(api_key, shown, 'reading', CLEARING)['noul']}
    else:
        wording = (f'Is the value of {job["expression"]} different from {job["claimed"]}?' if job['form'] == 'negated'
                   else f'Is {job["expression"]} equal to {job["claimed"]}?')
        reading = ask(api_key, STATE, 'answer', {'type': 'noul', 'instructions': wording})['noul']
        result = {'correct': (reading > 0.5) == job['holds'], 'reading': reading}

    print('.', end='', file=sys.stderr, flush=True)

    return {**{k: v for k, v in job.items() if k != 'options'}, **result}


print(f'{len(jobs)} calls', file=sys.stderr)

with ThreadPoolExecutor(max_workers=4) as pool:
    scored = list(pool.map(send, jobs))

print('', file=sys.stderr)

out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps({
    'source': 'sums generated here, seeded',
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'items': items,
    'scored': scored,
}, indent=2) + '\n')

rows = lambda op, digits, form: [s for s in scored if (s['op'], s['digits'], s['form']) == (op, digits, form)]
right = lambda found: f'{sum(s["correct"] for s in found)}/{len(found)}'
mean = lambda found: sum(s['reading'] for s in found) / len(found)

print(f'{"op":9} {"digits":6} {"choice":>7} {"true":>6} {"false":>6} {"yes on false":>13} {"clearing":>9}')

for op, digits in CELLS:
    print(f'{op:9} {digits:<6} {right(rows(op, digits, "choice")):>7} {right(rows(op, digits, "true")):>6} '
          f'{right(rows(op, digits, "false")):>6} {mean(rows(op, digits, "false")):>13.2f} '
          f'{mean(rows(op, digits, "clearing")):>9.2f}')

for op in ('+', '×'):
    negated = [s for s in scored if s['form'] == 'negated' and s['op'] == op]
    print(f'negated {op}: {right(negated)} right')
