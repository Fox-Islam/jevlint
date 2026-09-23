"""Record what jevlint puts on every corpus question, whether or not it fired.

`--all` reports the model checks that ran and cleared alongside the ones that
fired, so precision and recall can be computed without touching the catalogue
that other processes are reading.

Query files that carry a state are asked with it, so the state-scoped checks are
measured on the material the documentation ran them against. The files whose
state the page computes at run time carry none, and the run says which checks
that left out.

`--only=<check ids>` scores those checks and merges them into the readings
already recorded, leaving every other check's numbers where they were. A check
added to the catalogue is folded in for the price of itself, instead of buying
the whole corpus again and moving every published figure.

    python3 corpus/harvest.py [path/to/.env] [--only=<ids>] [--out=<file>]
"""
import json, os, pathlib, subprocess, sys
from datetime import datetime, timezone

# Where the key lives is the caller's business. TYPESAFE_API_KEY in the
# environment needs nothing; anywhere else, pass the file as the first argument
# or set JEVLINT_ENV_FILE.
args = [a for a in sys.argv[1:] if not a.startswith('--')]
out_path = pathlib.Path(next((a.split('=', 1)[1] for a in sys.argv[1:]
                              if a.startswith('--out=')), 'corpus/scores.json'))
env_file = (args[0] if args else os.environ.get('JEVLINT_ENV_FILE'))
if env_file and not pathlib.Path(env_file).is_file():
    sys.exit(f'No env file at {env_file}')
if not env_file and not os.environ.get('TYPESAFE_API_KEY'):
    sys.exit('Set TYPESAFE_API_KEY, or pass an env file: python3 corpus/harvest.py path/to/.env')

only = next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith('--only=')), None)

# A narrowed run adds to what is there. Starting from nothing would write out a
# file holding one check and read as every other check scoring zero.
held = json.loads(out_path.read_text()) if only and out_path.is_file() else {}
scored = held.get('scores', {})

# The readings in the file were paid for, and a narrowed run adds to them rather
# than replacing them, so the cost it records is the cost of the whole file.
calls = held.get('calls', 0)

# What this run has written. A narrowed run replaces the reading it already held
# for a check instead of taking the higher of the two, and a check asked
# several times about one question still keeps its strongest reading.
written = set()

for f in sorted(pathlib.Path('local/corpus').glob('*.json')):
    if f.name == 'all-scores.json':
        continue

    out = subprocess.run(
        ['php', 'php/bin/jevlint', 'check', str(f), '--all', '--format=json']
        + ([f'--only={only}'] if only else [])
        + ([f'--env-file={env_file}'] if env_file else []),
        capture_output=True, text=True).stdout

    if not out.strip():
        print(f'  {f.name}: no output', file=sys.stderr)
        continue

    d = json.loads(out)
    catalogue = d['catalogue']

    # A run that could not reach the API records nothing and must not be written
    # out as a tier of zeroes.
    if not d['summary'].get('complete', True):
        sys.exit(f'{f.stem}: {d["summary"]["unreachable"]} calls could not be made. Nothing written.')

    calls += d['summary']['calls']

    for finding in [*d['findings'], *d.get('cleared', [])]:
        if 'probability' not in finding:
            continue

        # A check asked more than once about one question - `query/overlapping-questions`
        # is asked per pair, `state/irrelevant-field` per field - produces several
        # readings. Keeping the last silently discarded the rest and understated the
        # check; the strongest reading is the one a run would have reported.
        key = f'{f.stem}/{finding["target"]}'
        at = scored.setdefault(key, {})
        check = finding['check']
        held = at.get(check, 0.0) if (key, check) in written else 0.0
        written.add((key, check))
        at[check] = max(held, finding['probability'])

    print(f'  {f.stem}: {d["summary"]["calls"]} calls', file=sys.stderr)

# The file this replaces is the evidence behind the published tables, so it is
# kept where a reader can diff the two.
if out_path.is_file():
    previous = pathlib.Path('local') / f'{out_path.stem}.previous.json'
    previous.parent.mkdir(exist_ok=True)
    previous.write_text(out_path.read_text())
    print(f'previous readings kept at {previous}', file=sys.stderr)

# Every report carries the catalogue that produced it so a changed rule set is
# visible instead of inferred. The evidence the published tables rest on needs
# the same stamp, or a reader cannot tell which catalogue it was measured with.
# corpus/README.md quotes what a harvest costs, and a reader deciding whether to
# pay for one needs that figure to be the one the last run paid.
# CorpusDocumentationTest pins the two together.
out_path.write_text(json.dumps({
    'catalogue': catalogue,
    'measured': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'calls': calls,
    'scores': scored,
}, indent=2) + '\n')
print(f'{len(scored)} questions scored, {calls} calls, written to {out_path}')
