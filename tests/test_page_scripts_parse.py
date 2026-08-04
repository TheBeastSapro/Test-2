"""Every page's inline JavaScript must parse.

## Why this test exists

`settings.html` declared `const esc` twice in one script block. That is a SyntaxError,
and a SyntaxError is refused at *parse* time — so nothing in the block ran. The panel
tabs never bound their click handlers, both agent cards sat on "Checking your sign-in..."
forever, and no connector could be tested. The page looked completely normal: every
control rendered, nothing was greyed out, and the only evidence was in a browser console
nobody had open.

Nothing in the Python suite could see it. The route returned 200, the template rendered,
the HTML contained every element a test might assert on — and the page was inert. That is
the shape of failure this file exists to catch: not a broken response, a broken *script*
inside a correct response.

So this renders each page the way a browser receives it and asks Node to parse what comes
back. It deliberately does not execute anything — there is no DOM here and running the
scripts would need one. Parsing is enough, because the bug class being caught is a whole
block that never runs at all.

The templates are checked *rendered* rather than as files, which is the point: a page's
scripts are assembled from a template plus whatever `base.html` contributes, and a
duplicate declaration across that seam only exists in the output.
"""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from forgecast.api.main import create_app
from forgecast.db import session_scope
from forgecast.models import Channel, User


@pytest.fixture
def client(user):
    """A signed-in browser. These pages redirect to /login when they are not."""
    with TestClient(create_app()) as test_client:
        token = test_client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "supersecret"},
        ).json()["access_token"]
        test_client.headers["Authorization"] = f"Bearer {token}"
        yield test_client

# Inline blocks only. A `src=` script is a static file the server does not assemble, and
# fetching it here would test the browser's loader rather than this app's templates.
_INLINE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node is needed to parse the rendered scripts; it ships with the app's "
           "own toolchain but is not required to run the Python suite",
)


def _pages(client) -> list[str]:
    """Every page a signed-in operator can open, including one channel hub.

    The channel page is included by id rather than by guessing a path, because it is the
    one page whose URL depends on data — and a page skipped for being awkward to reach is
    exactly where an unparsed script would survive.
    """
    with session_scope() as session:
        user = session.query(User).first()
        channel = session.query(Channel).first()
        if channel is None and user is not None:
            channel = Channel(user_id=user.id, name="Script Check", niche="test")
            session.add(channel)
            session.flush()
        channel_id = channel.id if channel is not None else None

    paths = ["/", "/settings", "/research", "/styles", "/skills-library",
             "/files", "/analytics", "/activity", "/setup"]
    if channel_id is not None:
        paths.append(f"/c/{channel_id}")
    return paths


def test_every_page_serves_javascript_that_parses(client, tmp_path):
    """One assertion, and it is worth more than its size.

    A failure here names the page and the parser's own message, which is what makes it
    actionable: `Identifier 'esc' has already been declared` points at the line, whereas
    the symptom it produces — "the tabs do not work" — points nowhere.
    """
    broken: list[str] = []

    for path in _pages(client):
        response = client.get(path, follow_redirects=True)
        assert response.status_code == 200, f"{path} did not render: {response.status_code}"

        for index, block in enumerate(_INLINE.findall(response.text)):
            if not block.strip():
                continue
            script = tmp_path / f"{path.strip('/').replace('/', '_') or 'root'}_{index}.js"
            script.write_text(block, encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(script)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                reason = next(
                    (line for line in result.stderr.splitlines() if "Error" in line),
                    result.stderr.strip().splitlines()[:1] or ["unparsed"],
                )
                broken.append(f"{path} (block {index}): {reason}")

    assert not broken, (
        "inline script blocks that a browser would refuse to run:\n  "
        + "\n  ".join(broken)
    )
