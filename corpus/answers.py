"""What Jev answers a decision-v7 question, scored against the label it ships.

decision-v7 asks both yes/no and choice questions, and the two are scored
differently. A Noul answers with the probability of yes, which is the
probability of a boolean label being true. A Choice answers with a winning label
and a probability for every option, and what a score needs is the probability on
the labelled option - not the probability on whichever option won, which is what
`probe` reports and which reads as a perfect answer whenever the model is
confidently wrong.

    from corpus.answers import ask, brier
"""
import json, os, pathlib, sys, time, urllib.error, urllib.request


def key(env_file=None):
    """`TYPESAFE_API_KEY`, from the environment or from the env file named."""
    if env_file and pathlib.Path(env_file).is_file():
        for line in pathlib.Path(env_file).read_text().splitlines():
            name, _, value = line.partition('=')

            if name.strip() == 'TYPESAFE_API_KEY':
                return value.strip().strip('"\'')

    found = os.environ.get('TYPESAFE_API_KEY')

    if not found:
        sys.exit('No TYPESAFE_API_KEY. Pass --env=<file> or set it.')

    return found


# A corpus run makes hundreds of calls, and the endpoint sheds load with a 429
# or a 5xx. Without this a run of an hour dies on one of them and pays again.
RETRIES = 4


def ask(api_key, state, qid, question):
    """One question against one state, as the raw answer the API returns."""
    asked = {k: v for k, v in question.items() if k in ('type', 'instructions', 'criteria')}
    body = json.dumps({'state': state, 'model': 'jev-latest', 'questions': {qid: asked}}).encode()
    # The endpoint refuses urllib's own User-Agent with a 403, which reads as a
    # rejected key and is not one.
    request = urllib.request.Request(
        'https://api.typesafe.ai/v1/systemone', data=body, headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'jevlint-corpus/1.0',
        })

    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)['answers'][qid]
        except urllib.error.HTTPError as refused:
            if refused.code < 429 or attempt == RETRIES - 1:
                raise

            time.sleep(2 ** attempt)

    raise RuntimeError('unreachable')


def scored(answer, label):
    """The probability the answer put on the label, and whether it picked it.

    Returns `None` for a question type with no label to score against, so a
    caller counts it out instead of scoring it as a hit.
    """
    if answer['type'] == 'noul' and isinstance(label, bool):
        probability = answer['noul'] if label else 1.0 - answer['noul']

        return probability, (answer['noul'] > 0.5) == label

    if answer['type'] == 'choice' and isinstance(label, str):
        return answer.get('probabilities', {}).get(label, 0.0), answer.get('choice') == label

    return None


def brier(rows):
    """Mean squared error against a label that is certain, so the truth is 1."""
    got = [p for p, _ in rows]

    return sum((1.0 - p) ** 2 for p in got) / len(got) if got else float('nan')
