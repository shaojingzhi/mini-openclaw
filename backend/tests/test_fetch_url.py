"""Unit tests for the fetch_url agent tool (US-006)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.tools.fetch_url import PARSE_FAILURE_MESSAGE, _clean_html, fetch_url


_FIXTURE_HTML = """
<!doctype html>
<html>
  <head>
    <title>Sample</title>
    <style>body { color: red; }</style>
    <script>console.log('secret');</script>
  </head>
  <body>
    <h1>Hello, OpenClaw</h1>
    <p>This is a <a href="https://example.com/x">link</a> in a paragraph.</p>
    <script>alert('still secret');</script>
    <ul>
      <li>one</li>
      <li>two</li>
    </ul>
  </body>
</html>
"""


class CleanHtmlTests(unittest.TestCase):
    def test_script_and_style_contents_are_stripped(self) -> None:
        out = _clean_html(_FIXTURE_HTML)
        self.assertNotIn("console.log", out)
        self.assertNotIn("alert(", out)
        self.assertNotIn("color: red", out)
        # The literal tag names should be gone too.
        self.assertNotIn("<script", out)
        self.assertNotIn("<style", out)

    def test_markdown_structure_is_preserved(self) -> None:
        out = _clean_html(_FIXTURE_HTML)
        self.assertIn("# Hello, OpenClaw", out)
        self.assertIn("[link](https://example.com/x)", out)
        self.assertIn("* one", out)
        self.assertIn("* two", out)


class FetchUrlToolTests(unittest.TestCase):
    def test_fetch_url_returns_cleaned_markdown(self) -> None:
        # Replace the whole _REQUESTS_TOOL module attribute with a stub for
        # the duration of the test. We can't patch a method on the live
        # RequestsGetTool/TextRequestsWrapper instances because both are
        # Pydantic-v2 models, and patch's teardown delattr() is rejected.
        stub = MagicMock()
        stub.invoke.return_value = _FIXTURE_HTML
        with patch("backend.tools.fetch_url._REQUESTS_TOOL", stub):
            out = fetch_url.invoke({"url": "https://example.invalid/page"})

        stub.invoke.assert_called_once_with({"url": "https://example.invalid/page"})
        self.assertIn("# Hello, OpenClaw", out)
        self.assertIn("[link](https://example.com/x)", out)
        self.assertNotIn("<script", out)
        self.assertNotIn("<style", out)
        # html2text strips trailing whitespace via our wrapper.
        self.assertFalse(out.endswith("\n"))

    def test_fetch_url_returns_clear_message_when_parse_fails(self) -> None:
        stub = MagicMock()
        stub.invoke.return_value = "<html>huge response</html>"
        with patch("backend.tools.fetch_url._REQUESTS_TOOL", stub), patch(
            "backend.tools.fetch_url._clean_html",
            side_effect=ValueError("parse failed"),
        ):
            out = fetch_url.invoke({"url": "https://example.invalid/page"})

        self.assertEqual(out, PARSE_FAILURE_MESSAGE)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
