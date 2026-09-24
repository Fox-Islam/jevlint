"""`choice/label-contradicts-description` and the probe's `keys-hidden`, measured.

Jev reads an option's label as part of what the option means. Where one option
plainly fits, the description decides; where none does, the label does. The
check reads a query for labels that name something other than their
descriptions, and the variant measures how far the labels move one answer.

  check   the check's own wordings, from the catalogue, asked the way the linter
          asks a question-scoped check: {instructions, criteria} as the state.
          Negatives are every distinct, fully described Choice somebody else
          wrote - decision-v7's option sets, the corpus tiers - plus this
          repository's other fixtures and examples and two sets in
          `labels.json`. Positives are each negative with its labels planted to
          contradict (every label moved one along, or the first two swapped),
          and the contradictions `labels.json` holds, on which the check's
          locator is also asked and scored against the labels each names.

  names   the query that raised this, as reported and with the option describing
          Discord taken out, asked three times each: once with its labels as
          written, once hidden, once beside a true catch-all.
          Then `letters`, six questions over one state, asked three times.

  probe   decision-v7 Choice questions whose options are all described, as
          written and with labels planted, asked five times and then with the
          labels hidden. A move counts the way `jevlint probe` counts one: past
          three times the repeat spread, floored at 0.0085, and past 0.05.

    python3 corpus/labels.py check [--env=.env] [--out=local/labels-check.json]
    python3 corpus/labels.py names [--env=.env] [--out=local/labels-names.json]
    python3 corpus/labels.py probe [--clean=12] [--planted=6] [--env=.env] [--out=local/labels-probe.json]
"""
import json, pathlib, random, statistics, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from answers import key

CHECK = 'choice/label-contradicts-description'
SEED = 20260924
FLOOR, NEGLIGIBLE = 0.0085, 0.05

experiment = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else sys.exit(__doc__)
arg = lambda name, default: next((a.split('=', 1)[1] for a in sys.argv[2:] if a.startswith(f'--{name}=')), default)
out_path = pathlib.Path(arg('out', f'local/labels-{experiment}.json'))
api_key = key(arg('env', '.env' if pathlib.Path('.env').is_file() else None))

dataset = pathlib.Path('local/decision-v7-test.jsonl')

if not dataset.is_file():
    sys.exit(f'{dataset} is not there. Run `python3 corpus/decision.py` first; it fetches the dataset.')

rows = [json.loads(line) for line in dataset.open()]


def send(state, questions):
    """Several questions against one state, the way the linter batches a check's wordings."""
    body = json.dumps({'state': state, 'model': 'jev-latest', 'questions': questions}).encode()
    request = urllib.request.Request('https://api.typesafe.ai/v1/systemone', data=body, headers={
        'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json', 'User-Agent': 'jevlint-corpus/1.0'})

    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)['answers']
        except urllib.error.HTTPError as refused:
            if refused.code < 429 or attempt == 3:
                raise

            time.sleep(2 ** attempt)


def described(criteria):
    return (isinstance(criteria, dict) and len(criteria) > 1 and len(set(map(str, criteria.values()))) == len(criteria)
            and all(isinstance(v, str) and v.strip() for v in criteria.values()))


def planted(criteria, how):
    """The same descriptions under labels that contradict them."""
    labels, descriptions = list(criteria), list(criteria.values())

    if how == 'moved':
        return {labels[(i + 1) % len(labels)]: d for i, d in enumerate(descriptions)}

    labels[0], labels[1] = labels[1], labels[0]

    return dict(zip(labels, descriptions))


def choices(value):
    if isinstance(value, dict):
        if value.get('type') == 'choice':
            yield value

        for inner in value.values():
            yield from choices(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from choices(inner)


def pool(rs, variant):
    return [r for r in rs if r['_meta'].get('variant') == variant and next(iter(r['questions'].values()))['type'] == 'choice'
            and described(next(iter(r['questions'].values())).get('criteria'))]


def family(r):
    return tuple(next(iter(r['questions'].values()))['criteria'])


mean = lambda xs: sum(xs) / len(xs) if xs else float('nan')
stamp = {'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'), 'seed': SEED}

if experiment == 'check':
    entry = next(c for c in json.load(open('checks/catalogue.json'))['checks'] if c['id'] == CHECK)
    wordings = {f'w{i}': w for i, w in enumerate(entry['questions'])}

    written = [next(iter(r['questions'].values())) for r in {family(r): r for r in pool(rows, 'clean')}.values()]

    for f in ('corpus/gold.json', 'corpus/docs-examples.json', 'corpus/field.json', 'examples/support-triage.json'):
        written += list(choices(json.load(open(f))))

    written += [f[k] for f in json.load(open('checks/fixtures.json'))['fixtures'] if f['check'] != CHECK
                for k in ('clean', 'fixed') if k in f and f[k].get('type') == 'choice']
    extra = json.load(open('corpus/labels.json'))
    written += list(extra['negative'].values())
    negatives = list({json.dumps([q['instructions'], q['criteria']]): q for q in written if described(q.get('criteria'))}.values())

    cases = [('clean', q['criteria'], q) for q in negatives]
    cases += [(how, planted(q['criteria'], how), q) for how in ('moved', 'swapped') for q in negatives]
    cases += [('written', q['criteria'], q) for q in extra['positive'].values()]
    locator = {'type': 'choice', 'instructions': entry['locate']}

    def read(case):
        kind, criteria, question = case
        # The locator goes in the same call as the wordings, as the linter sends it.
        asked = wordings | ({'where': locator | {'criteria': criteria}} if kind == 'written' else {})
        answers = send({'instructions': question['instructions'], 'criteria': criteria}, asked)
        where = answers.pop('where', None)
        picked = max(where['probabilities'], key=where['probabilities'].get) if where else None

        return {'kind': kind, 'labels': list(criteria), 'reading': mean([a['noul'] for a in answers.values()]),
                'located': picked, 'located_right': picked in question.get('contradicts', []) if picked else None}

    with ThreadPoolExecutor(max_workers=4) as workers:
        scored = list(workers.map(read, cases))

    out_path.write_text(json.dumps(stamp | {'trigger': entry['trigger'], 'scored': scored}, indent=2) + '\n')

    located = [s for s in scored if s['kind'] == 'written']
    print(f"locator names a contradicting label on {sum(s['located_right'] for s in located)} of {len(located)}")

    for kind in ('clean', 'moved', 'swapped', 'written'):
        group = [s for s in scored if s['kind'] == kind]
        fired = [s for s in group if s['reading'] > entry['trigger']]
        print(f"{kind:8s} {len(fired):2d} of {len(group):2d} fire at {entry['trigger']}, "
              f"readings {min(s['reading'] for s in group):.2f} to {max(s['reading'] for s in group):.2f}")

        for s in (group if kind == 'clean' else [s for s in group if s not in fired]):
            if kind != 'clean' or s in fired:
                print(f"           {s['reading']:.2f}  {', '.join(s['labels'])}")

elif experiment == 'names':
    reported = json.load(open('corpus/labels.json'))['positive']['discord']
    as_written = reported['criteria']
    without = {k: v for k, v in as_written.items() if k != 'youtube'}
    arms = {
        'as reported': as_written,
        'the option describing Discord taken out': without,
        'the same, labels hidden': {f'option_{i + 1}': v for i, v in enumerate(without.values())},
        'the same, with a true catch-all': without | {'none': 'None of the other options is true'},
    }

    def read(arm):
        return arm, send("I'm using Discord", {'q': {'type': 'choice', 'instructions': reported['instructions'],
                                                      'criteria': arms[arm]}})['q']['probabilities']

    with ThreadPoolExecutor(max_workers=4) as workers:
        scored = list(workers.map(read, [arm for arm in arms for _ in range(3)]))

    out_path.write_text(json.dumps(stamp | {'scored': scored}, indent=2) + '\n')

    for arm in arms:
        runs = [p for a, p in scored if a == arm]
        print(f'{arm:42s} ' + '  '.join(f'{label} {min(r[label] for r in runs):.2f}-{max(r[label] for r in runs):.2f}'
                                         for label in arms[arm]))

    letters = json.load(open('corpus/labels.json'))['letters']
    runs = [send(letters['state'], letters['questions']) for _ in range(3)]
    out_path.write_text(json.dumps(stamp | {'scored': scored, 'letters': runs}, indent=2) + '\n')

    for qid, question in letters['questions'].items():
        print(f'{qid:42s} ' + '  '.join(
            f"{label!r} {min(r[qid]['probabilities'][label] for r in runs):.2f}-{max(r[qid]['probabilities'][label] for r in runs):.2f}"
            for label in question['criteria']))

else:
    rnd = random.Random(SEED)
    by = {}

    for r in pool(rows, 'clean'):
        by.setdefault(family(r), []).append(r)

    per = {'clean': int(arg('clean', '12')), 'moved': int(arg('planted', '6')), 'swapped': int(arg('planted', '6'))}
    cases = [(kind, r) for kind in per for f in sorted(by) for r in rnd.sample(by[f], min(per[kind], len(by[f])))]

    def ask(state, instructions, criteria):
        return send(state, {'q': {'type': 'choice', 'instructions': instructions, 'criteria': criteria}})['q']['probabilities']

    def probe(case):
        kind, r = case
        question = next(iter(r['questions'].values()))
        criteria = question['criteria'] if kind == 'clean' else planted(question['criteria'], kind)
        repeats = [ask(r['state'], question['instructions'], criteria) for _ in range(5)]
        winner = max(repeats[0], key=repeats[0].get)
        position = list(criteria).index(winner)
        hidden = ask(r['state'], question['instructions'], {f'option_{i + 1}': v for i, v in enumerate(criteria.values())})
        readings = [a.get(winner, 0.0) for a in repeats]
        floor = max(statistics.stdev(readings), FLOOR)
        moved = abs(hidden.get(f'option_{position + 1}', 0.0) - mean(readings))

        return {'kind': kind, 'id': r['_meta']['id'], 'label': question['label'], 'winner': winner,
                'touched': kind == 'moved' or question['label'] in list(question['criteria'])[:2],
                'repeats': readings, 'hidden': hidden.get(f'option_{position + 1}', 0.0),
                'moved': moved, 'counted': moved > 3 * floor and moved >= NEGLIGIBLE}

    with ThreadPoolExecutor(max_workers=4) as workers:
        scored = list(workers.map(probe, cases))

    out_path.write_text(json.dumps(stamp | {'calls': 6 * len(scored), 'scored': scored}, indent=2) + '\n')

    for kind in per:
        group = [s for s in scored if s['kind'] == kind]
        print(f"{kind:8s} {sum(s['counted'] for s in group):2d} of {len(group):2d} counted, "
              f"median move {statistics.median(s['moved'] for s in group):.3f}")

        if kind == 'swapped':
            for touched in (True, False):
                part = [s for s in group if s['touched'] == touched]
                print(f"           the swap {'takes in' if touched else 'leaves out'} the labelled answer: "
                      f"{sum(s['counted'] for s in part)} of {len(part)} counted")
