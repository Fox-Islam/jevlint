"""What the catalogue's second questions change: `cleared_by` and `fired_by`.

A check's wordings are averaged, because they mean the same thing. A second
question means something else - "is this a question of fact?" beside "is picking
between these options guessing?" - so it decides on its own: `cleared_by` sets a
finding aside where it reads above its trigger, and `fired_by` raises one the
check's own reading did not.

Two measurements, each asking the check's own wording and its second question
over the same cases:

  undetermined  `choice/undetermined-outcome` and its `cleared_by`, over the
                hidden draws `jev-does-not-play-dice` recorded, outcomes written
                here that are still to happen or settled and withheld, questions
                of general knowledge, the six MMLU items from the jevlint-tests
                benchmark, and every Choice question in the corpus docs tier
  arithmetic    `question/arithmetic` and its `fired_by`, over the Bayes and
                negation items from the same benchmark, every question in the
                docs and field tiers, the rule questions `mechanical.py` asks,
                and comparisons written here whose figures are already stated

The benchmark is https://github.com/nunezb/jevlint-tests, fetched on demand at
the commit this was measured against. Its MMLU items are MIT, from Hendrycks et
al.; its Bayes and negation items are CC BY 4.0.

    python3 corpus/second.py [--repeats=2] [--env=.env] [--out=local/second-scores.json]
"""
import json, pathlib, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from answers import ask, key

BENCHMARK = 'https://raw.githubusercontent.com/nunezb/jevlint-tests/ac5a968236258ef7f3fbe1ead501cfd36e6a9d1f/queries'
DICE = 'https://raw.githubusercontent.com/KantaHayashiAI/jev-does-not-play-dice/main/data/requests/dice.jsonl'

arg = lambda name, default: next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith(f'--{name}=')), default)
repeats = int(arg('repeats', '2'))
out_path = pathlib.Path(arg('out', 'local/second-scores.json'))
api_key = key(arg('env', '.env' if pathlib.Path('.env').is_file() else None))

if not pathlib.Path('local/corpus').is_dir():
    sys.exit('local/corpus is not there. Run `python3 corpus/build.py` first.')

catalogue = {c['id']: c for c in json.loads(pathlib.Path('checks/catalogue.json').read_text())['checks']}


def fetched(url, name):
    local = pathlib.Path('local/second') / name

    if not local.is_file():
        local.parent.mkdir(parents=True, exist_ok=True)
        print(f'fetching {url}', file=sys.stderr)
        urllib.request.urlretrieve(url, local)

    return local


def benchmark(name):
    return json.loads(fetched(f'{BENCHMARK}/{name}.json', f'{name}.json').read_text())


def options(*labels):
    return {label: f'The answer is {label}' for label in labels}


def choice(instructions, criteria):
    return {'type': 'choice', 'instructions': instructions, 'criteria': criteria}


def noul(instructions):
    return {'type': 'noul', 'instructions': instructions}


# Outcomes the material leaves open, written here because every recorded one is
# a draw. The first two are still to happen; the rest are settled and withheld,
# which the check's own criteria name as undetermined.
UNSETTLED = {
    'future/parcel': ('Parcel 88213 left the Leeds depot at 18:40 on Tuesday. The van is on a route with nine '
                      'other drops. No delivery attempt has been recorded.',
                      choice('Which of these will happen to the parcel?', {
                          'delivered': 'It is delivered on the first attempt',
                          'carded': 'Nobody is in and a card is left',
                          'refused': 'The recipient refuses it',
                          'other': 'Anything the other options do not cover'})),
    'future/ticket': ('Ticket 4471, opened this morning: "The export button does nothing." No engineer has '
                      'picked it up yet.',
                      choice('Which team will end up closing this ticket?', {
                          'support': 'Support closes it without escalating',
                          'engineering': 'Engineering closes it after a fix',
                          'billing': 'Billing closes it',
                          'other': 'Anything the other options do not cover'})),
    'withheld/match': ('Rovers played United yesterday evening. The final score has been published but is not '
                       'included here.', choice('Who won the match?', options('Rovers', 'United', 'draw'))),
    'withheld/envelope': ('The committee chose one of three candidates last week. The name is sealed in an '
                          'envelope until Friday.', choice('Which candidate was chosen?', options('Ahmed', 'Brooke', 'Chen'))),
    'withheld/blood': ('Patient 2291 was admitted on Monday. Their blood type was recorded at admission.',
                       choice("What is the patient's blood type?", options('A', 'B', 'AB', 'O'))),
}

# Questions of fact, which the material and general knowledge settle
KNOWN = {
    'fact/capital': ('A student is revising geography.',
                     choice('What is the capital of Australia?', options('Sydney', 'Canberra', 'Melbourne', 'Perth'))),
    'fact/element': ('Which element has the atomic number 74?',
                     choice('Which option is the correct answer to the question above?',
                            options('tungsten', 'tantalum', 'rhenium', 'osmium'))),
}

# Comparisons whose figures are all written down, which the arithmetic check
# exempts: Jev answered 30 of 30 threshold questions on decision-v7
STATED = {
    'stated/threshold': noul('Is the reported blood pressure of 150 above the 140 limit?'),
    'stated/compare': noul('Is the invoice total of £420 higher than the quoted £400?'),
    'stated/count': noul('Does the order list more than one item?'),
    'stated/percent': noul('The report says the error rate is 4%. Is it below the 5% target?'),
}


def undetermined_cases():
    """(name, kind, question, state), kind being what the second question should do."""
    draws = {}

    for line in fetched(DICE, 'dice.jsonl').open():
        row = json.loads(line)
        draws.setdefault(row['group'], row['request'])

    for group, request in sorted(draws.items()):
        yield f'draw/{group}', 'keep', request['questions']['answer'], request['state']

    for name, (state, question) in UNSETTLED.items():
        yield name, 'keep', question, state

    for name, (state, question) in KNOWN.items():
        yield name, 'clear', question, state

    for i in range(6):
        query = benchmark(f'q_clean_0{i}')
        yield f'mmlu/{i}', 'clear', query['questions']['answer'], query['state']

    for path in sorted(pathlib.Path('local/corpus').glob('docs_ex_state_*.json')):
        query = json.loads(path.read_text())

        for qid, question in query['questions'].items():
            if question.get('type') == 'choice':
                yield f'{path.stem}/{qid}', 'settled', question, query.get('state', '')


def arithmetic_cases():
    """(name, kind, question), kind being what the second question should do."""
    for group, count in (('bayes_claims', 5), ('negation', 4)):
        for i in range(count):
            for qid, question in benchmark(f'q_{group}_0{i}')['questions'].items():
                yield f'{group}/{i}/{qid}', 'fire', question

    for qid, question in json.loads(pathlib.Path('local/corpus/docs_ex.json').read_text())['questions'].items():
        yield f'docs/{qid}', 'quiet', question

    for path in sorted(pathlib.Path('local/corpus').glob('bench-*.json')):
        for qid, question in json.loads(path.read_text())['questions'].items():
            yield f'{path.stem}/{qid}', 'quiet', question

    source = pathlib.Path('corpus/mechanical.py').read_text()
    rules = {}
    exec(source[source.index('RULES = {'):source.index('\n\ndef state')], rules)

    for name, (text, _) in rules['RULES'].items():
        yield f'rule/{name}', 'quiet', noul(text)

    for name, question in STATED.items():
        yield name, 'quiet', question


def shown_question(question):
    """What a question-scoped check is shown: the instructions and criteria, no id or type."""
    shown = {'instructions': question.get('instructions', '')}

    if question.get('criteria'):
        shown['criteria'] = question['criteria']

    return shown


def wordings(check_id, second):
    check = catalogue[check_id]

    return {'check': (check.get('questions') or [check['question']])[0], 'second': check[second]['question']}


UNDETERMINED = wordings('choice/undetermined-outcome', 'cleared_by')
ARITHMETIC = wordings('question/arithmetic', 'fired_by')

jobs = []

for name, kind, question, state in undetermined_cases():
    for asked in ('check', 'second'):
        for _ in range(repeats):
            jobs.append(('undetermined', name, kind, asked, UNDETERMINED[asked],
                         json.dumps({'question': shown_question(question), 'state': state}, ensure_ascii=False)))

for name, kind, question in arithmetic_cases():
    for asked in ('check', 'second'):
        for _ in range(repeats):
            jobs.append(('arithmetic', name, kind, asked, ARITHMETIC[asked],
                         json.dumps(shown_question(question), ensure_ascii=False)))


def send(job):
    measurement, name, kind, asked, wording, state = job
    reading = ask(api_key, state, 'reading', wording)['noul']
    print('.', end='', file=sys.stderr, flush=True)

    return {'measurement': measurement, 'case': name, 'kind': kind, 'asked': asked, 'reading': reading}


print(f'{len(jobs)} calls', file=sys.stderr)

with ThreadPoolExecutor(max_workers=4) as pool:
    scored = list(pool.map(send, jobs))

print('', file=sys.stderr)

out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps({
    'source': 'jevlint-tests at ac5a968, jev-does-not-play-dice, the corpus docs and field tiers, and cases written here',
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'repeats': repeats,
    'scored': scored,
}, indent=2) + '\n')

mean = lambda xs: sum(xs) / len(xs)
readings = {}

for row in scored:
    readings.setdefault((row['measurement'], row['case'], row['kind']), {}).setdefault(row['asked'], []).append(row['reading'])

cases = {k: {asked: mean(v) for asked, v in by.items()} for k, by in readings.items()}

for measurement, check_id, second in (('undetermined', 'choice/undetermined-outcome', 'cleared_by'),
                                      ('arithmetic', 'question/arithmetic', 'fired_by')):
    trigger = catalogue[check_id]['trigger']
    second_trigger = catalogue[check_id][second]['trigger']
    print(f'\n{check_id}: the check against {trigger:.2f}, its `{second}` against {second_trigger:.2f}')

    for kind in sorted({k for (m, _, k) in cases if m == measurement}):
        rows = [v for (m, _, k), v in cases.items() if m == measurement and k == kind]
        fires = sum(v['check'] > trigger for v in rows)
        above = sum(v['second'] > second_trigger for v in rows)
        print(f'  {kind:8} {len(rows):3} cases  check fires {fires:3}  second {min(v["second"] for v in rows):.2f} '
              f'to {max(v["second"] for v in rows):.2f}, above its trigger {above}')

    if measurement == 'undetermined':
        verdict = lambda v: v['check'] > trigger and v['second'] <= second_trigger
    else:
        verdict = lambda v: v['check'] > trigger or v['second'] > second_trigger

    for kind in sorted({k for (m, _, k) in cases if m == measurement}):
        rows = [v for (m, _, k), v in cases.items() if m == measurement and k == kind]
        print(f'  {kind:8} a finding on {sum(verdict(v) for v in rows)} of {len(rows)} with the second question, '
              f'{sum(v["check"] > trigger for v in rows)} without')
