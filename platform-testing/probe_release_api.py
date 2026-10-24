"""Record unauthenticated runner connectivity, independently of the packaged app."""

import json
import ssl
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

request = Request("https://api.github.com/repos/bwsinger/mpc-autofill/releases/latest",
                  headers={"Accept": "application/vnd.github+json", "User-Agent": "mpc-autofill"})
try:
    with urlopen(request, timeout=10) as response:
        report = {"status": response.status, "headers": dict(response.headers), "tag": json.load(response)["tag_name"]}
except HTTPError as error:
    report = {"status": error.code, "headers": dict(error.headers), "body": error.read().decode("utf-8")}
except Exception as error:
    report = {"error": repr(error), "ssl_paths": str(ssl.get_default_verify_paths())}
text = json.dumps(report, indent=2)
Path("public-release-api.log").write_text(text, encoding="utf-8")
print(text)
