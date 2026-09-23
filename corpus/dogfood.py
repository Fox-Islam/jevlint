"""Turn the catalogue's own model checks into query files jevlint can check.

The checks are Jev questions, so the linter can be run on them. Each wording of
each model check becomes a question in one of two files, and what those files
hold as state is what the check would be shown in a real run: a question under
review for the question-scoped ones, a question and its state for the rest.

    python3 corpus/dogfood.py
    php php/bin/jevlint check local/catalogue-question-checks.json
    php php/bin/jevlint check local/catalogue-state-checks.json

The state carries an unread field, `routing`, so the state checks
have something to find. `state/irrelevant-field` reports it, correctly, and that
finding is an artefact of this file rather than a defect in the catalogue.
"""
import json, pathlib

cat = json.loads(pathlib.Path('checks/catalogue.json').read_text())
checks = [c for c in cat['checks'] if c['mode'] == 'model']

def key(cid):
    return cid.replace('/', '_').replace('-', '_')

# What a question-scoped check is shown: the question under review.
question_scope = {
    "state": {
        "instructions": "Does the customer say they cannot carry on using the product?",
        "criteria": {
            "true": "The customer states they are unable to do something they need to do.",
            "false": "The customer can still use the product, even if something is inconvenient."
        }
    },
    "questions": {}
}

# What a state-scoped check is shown: the question in full, criteria included,
# and the real state behind it. `Query::stateWith` builds the same shape.
state_scope = {
    "state": {
        "question": {
            "instructions": "Does the customer ask for a refund?",
            "criteria": {
                "true": "The customer asks for money back, a refund, or a charge to be reversed.",
                "false": "The customer reports a problem without asking for money back."
            }
        },
        "state": {
            "ticket": "I was charged twice for order A-104. Please refund the duplicate.",
            "routing": {"cdn_pop": "lhr-3", "shard": 7}
        }
    },
    "questions": {}
}

for c in checks:
    # A composite check has one entry per wording, so every wording is linted.
    wordings = c.get('questions') or [c['question']]
    for i, w in enumerate(wordings):
        q = dict(w)
        # The per-field check carries a placeholder; fill it the way the linter does.
        if '{field}' in q['instructions']:
            q['instructions'] = q['instructions'].replace('{field}', 'routing')
        name = key(c['id']) + (f'_w{i}' if len(wordings) > 1 else '')
        target = question_scope if c['scope'] == 'question' else state_scope
        target['questions'][name] = q

out = pathlib.Path('local')
out.mkdir(exist_ok=True)
(out / 'catalogue-question-checks.json').write_text(json.dumps(question_scope, indent=2) + "\n")
(out / 'catalogue-state-checks.json').write_text(json.dumps(state_scope, indent=2) + "\n")
print(f"{len(question_scope['questions'])} question-scoped checks, {len(state_scope['questions'])} state-scoped")
