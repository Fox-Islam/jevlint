"""Mirror the documentation pages the corpus was lifted from, for `states.py`.

The pages are not committed: they are TypeSafe's, they change, and the corpus
records what was read from them rather than the reading. `llms.txt` lists every
page, and a page id in `docs-examples.json` is its path with `/` and `-` as `_`.

    python3 corpus/pages.py [--out=local/docs]
"""
import json, pathlib, sys, urllib.request

INDEX = 'https://docs.typesafe.ai/llms.txt'
OUT = pathlib.Path(next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith('--out=')), 'local/docs'))

import re

index = urllib.request.urlopen(INDEX).read().decode()
urls = sorted(set(re.findall(r'https://docs\.typesafe\.ai/[A-Za-z0-9_/.-]+\.md', index)))
ident = lambda path: path.replace('/', '_').replace('#', '_').replace('-', '_')
by_id = {ident(u.removeprefix('https://docs.typesafe.ai/').removesuffix('.md')): u for u in urls}

wanted = sorted({entry['page'] for entry in json.loads(pathlib.Path('corpus/docs-examples.json').read_text()).values()})
OUT.mkdir(parents=True, exist_ok=True)
missing = []

for page in wanted:
    url = by_id.get(page)

    if url is None:
        missing.append(page)
        continue

    urllib.request.urlretrieve(url, OUT / f'{page}.md')

print(f'{len(wanted) - len(missing)} of {len(wanted)} pages in {OUT}')

if missing:
    print('not in the index: ' + ', '.join(missing), file=sys.stderr)
    sys.exit(1)
