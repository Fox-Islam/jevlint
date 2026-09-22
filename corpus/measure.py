"""Precision and recall per check, against the labelled corpus"""
import hashlib, json, pathlib, subprocess, collections

_catalogue = pathlib.Path('checks/catalogue.json').read_bytes()
cat = json.loads(_catalogue)
trigger = {c['id']: c.get('trigger', 0.7) for c in cat['checks'] if c['mode'] == 'model'}
_fingerprint = hashlib.sha256(_catalogue).hexdigest()[:12]

# Asked for, not recomputed: PHP and Python encode JSON differently enough that
# two implementations of one digest disagree, and a stamp nobody can reproduce is
# worse than none.
_catalogue_asked = json.loads(subprocess.run(
    ['php', 'php/bin/jevlint', '--version', '--format=json'],
    capture_output=True, text=True).stdout)['catalogue']['asked']

_raw = json.loads(pathlib.Path('corpus/scores.json').read_text())
# The file gained a catalogue stamp; older ones are the bare mapping.
scored = _raw['scores'] if 'scores' in _raw else _raw
_stamp = _raw.get('catalogue', {}) if 'scores' in _raw else {}
docs = json.loads(pathlib.Path('corpus/docs-examples.json').read_text())

# The docs repeat the same example across pages; count each question once
_norm = lambda k: k.replace('/', '_').replace('#', '_').replace('-', '_')
_seen, _drop = set(), set()
for _name, _q in docs.items():
    if _q['instructions'] in _seen:
        _drop.add(_norm(_name))
    _seen.add(_q['instructions'])
# The question id, not the whole score id: the docs tier is several files now.
scored = {k: v for k, v in scored.items() if k.partition('/')[2] not in _drop}
gold = json.loads(pathlib.Path('corpus/gold.json').read_text())

def key(name):
    return name.replace('/', '_').replace('#', '_').replace('-', '_')

# Which corpus tier each scored question belongs to
tiers = {}
for qid in scored:
    f, target = qid.split('/', 1)
    tiers[qid] = 'gold' if f == 'gold' else 'docs' if f.startswith('docs_ex') else 'field'

gold_by_target = {key(name): g for name, g in gold.items()}

rows, detail = [], {}
for check in sorted(trigger):
    t = trigger[check]
    fired = {tier: 0 for tier in ('gold-good', 'docs', 'field')}
    total = {tier: 0 for tier in ('gold-good', 'docs', 'field')}
    # A reading within this of its trigger may not survive the next run, so a
    # count of fires made of them is a count of coin flips.
    NEAR = 0.1
    shaky = {tier: 0 for tier in ('gold-good', 'docs', 'field')}
    caught = missed = never_ran = 0
    caught_quoted = quoted_n = 0

    for qid, probs in scored.items():
        f, target = qid.split('/', 1)
        p = probs.get(check)
        if f == 'gold':
            g = gold_by_target.get(target)
            if g is None:
                continue
            if g['label'] == 'bad':
                if check in g['defects']:
                    if p is None:
                        never_ran += 1
                    else:
                        caught += p > t
                        missed += p <= t
                        if g.get('tier') == 'quoted':
                            quoted_n += 1
                            caught_quoted += p > t
                continue
            if check not in g.get('clears', []):
                continue
            bucket = 'gold-good'
        else:
            bucket = 'docs' if f.startswith('docs_ex') else 'field'
        # A check the linter never asked about this question is not a check that
        # cleared it. Counting it as one turns silence into a clean bill of health.
        if p is None:
            continue
        total[bucket] += 1
        fired[bucket] += p > t
        # Of the fires, not of every reading. Counting the whole denominator made
        # the published counts 2 to 6 times what the legend below claims, and in
        # one cell more shaky readings than there were fires.
        shaky[bucket] += p > t and abs(p - t) <= NEAR

    clean_total = total['gold-good'] + total['docs']
    clean_fired = fired['gold-good'] + fired['docs']
    clean_shaky = shaky['gold-good'] + shaky['docs']
    rows.append((check, caught, caught + missed, never_ran, clean_fired, clean_total,
                 fired['field'], total['field']), )
    detail[check] = (caught_quoted, quoted_n, clean_shaky, shaky['field'])

if _stamp:
    print(f"measured against catalogue v{_stamp.get('version')} {_stamp.get('fingerprint')} "
          f"for {_stamp.get('model')}, on {_raw.get('measured')}\n")

# The triggers below come from the catalogue on disk and the readings from the
# stored run. Where the two asked different questions, every rate is a threshold
# applied to answers that were never given to it. The whole-file fingerprint moves
# when a message is reworded, which is not a reason to spend the calls again, so
# the comparison is against the fingerprint over what the checks ask.
if _stamp.get('asked') and _stamp['asked'] != _catalogue_asked:
    print(f"The checks now ask something else. These readings were harvested from "
          f"{_stamp['asked']} and the catalogue asks {_catalogue_asked}. "
          f"Re-run corpus/harvest.py to measure the check set you have.\n")
elif _stamp and _stamp.get('fingerprint') not in (None, _fingerprint):
    # An older harvest recorded no digest of what was asked, so nothing here can
    # say whether the questions moved with the file.
    known = 'what the checks ask has not changed' if _stamp.get('asked') \
        else 'this harvest predates the digest of what the checks ask, so nothing here can tell'
    print(f"The catalogue file is now {_fingerprint}, harvested from {_stamp.get('fingerprint')}: "
          f"{known}.\n")

print(f"{'check':34} {'recall':>7} {'quoted':>7}  {'docs-correct':>14} {'±0.1':>5}  "
      f"{'field':>9} {'±0.1':>5}")
for check, caught, gold_n, never_ran, cf, ct, ff, ft in sorted(rows, key=lambda r: (r[4] / max(r[5], 1))):
    recall = f"{caught}/{gold_n}" if gold_n else "-"
    cq, qn, cs, fs = detail[check]
    quoted = f"{cq}/{qn}" if qn else "-"
    print(f"{check:34} {recall:>7} {quoted:>7}  {cf:>4}/{ct:<4} {cf/max(ct,1)*100:>4.0f}% "
          f"{cs:>5}  {ff:>4}/{ft:<4} {fs:>5}")

skipped = [(c, n) for c, _, _, n, _, _, _, _ in rows if n]
unasked = [(c, ct) for c, _, _, _, _, ct, _, _ in rows if ct == 0]
print('\n`docs-correct` is the docs tier plus the gold entries labelled good, counted for a '
      'check only where that entry\'s `clears` names it, so a denominator runs from the 52 '
      'distinct docs questions to 54.'
      '\n`quoted` counts only the gold negatives the documentation gives an example for; the '
      'rest are written from its definition.\n`±0.1` counts the fires whose reading sits within '
      '0.1 of the trigger, which may not repeat.')

if unasked:
    print('\nNever asked about any question in the clean tiers, so the rates above say '
          'nothing about them:')
    for c, _ in unasked:
        print(f'  {c}')
if skipped:
    print('\nNever asked about a gold question that names them as its defect:')
    for c, n in skipped:
        print(f'  {c}: {n}')
