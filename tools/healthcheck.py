import os
import tomllib
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

site = tomllib.loads(Path(os.environ['SHIJIE_CONFIG']).read_text())['site']
url = urlsplit(site['public_url'])
req = Request('http://127.0.0.1:8093' + url.path.rstrip('/') + '/health/ready',
              headers={'Host': url.netloc, 'X-Forwarded-Proto': url.scheme})
with urlopen(req, timeout=4) as response:
    assert response.status == 200
