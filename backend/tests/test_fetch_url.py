"""Unit tests for the fetch_url agent tool (US-006)."""

from __future__ import annotations

from ipaddress import ip_address
import unittest
from unittest.mock import MagicMock, patch

from backend.tools.fetch_url import (
    BLOCKED_URL_MESSAGE,
    PARSE_FAILURE_MESSAGE,
    _clean_html,
    fetch_url,
)


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
        with patch("backend.tools.fetch_url._fetch_text", return_value=_FIXTURE_HTML) as fetch_text:
            out = fetch_url.invoke({"url": "https://example.invalid/page"})

        fetch_text.assert_called_once_with("https://example.invalid/page")
        self.assertIn("# Hello, OpenClaw", out)
        self.assertIn("[link](https://example.com/x)", out)
        self.assertNotIn("<script", out)
        self.assertNotIn("<style", out)
        # html2text strips trailing whitespace via our wrapper.
        self.assertFalse(out.endswith("\n"))

    def test_fetch_url_returns_clear_message_when_parse_fails(self) -> None:
        with patch("backend.tools.fetch_url._fetch_text", return_value="<html>huge response</html>"), patch(
            "backend.tools.fetch_url._clean_html",
            side_effect=ValueError("parse failed"),
        ):
            out = fetch_url.invoke({"url": "https://example.invalid/page"})

        self.assertEqual(out, PARSE_FAILURE_MESSAGE)

    def test_blocks_loopback_private_and_non_http_urls_before_request(self) -> None:
        for url in ("http://127.0.0.1:8002/health", "http://10.0.0.1", "file:///etc/passwd"):
            with self.subTest(url=url), patch("backend.tools.fetch_url.requests.get") as get:
                self.assertEqual(fetch_url.invoke({"url": url}), BLOCKED_URL_MESSAGE)
                get.assert_not_called()

    def test_blocks_hostname_that_resolves_to_private_address(self) -> None:
        with patch("backend.tools.fetch_url._resolve_host", return_value={ip_address("192.168.1.10")}), patch(
            "backend.tools.fetch_url.requests.get"
        ) as get:
            out = fetch_url.invoke({"url": "http://internal.example"})

        self.assertEqual(out, BLOCKED_URL_MESSAGE)
        get.assert_not_called()

    def test_validates_redirect_targets_before_following_them(self) -> None:
        redirect = MagicMock(status_code=302, headers={"Location": "http://127.0.0.1:8002/health"})
        with patch("backend.tools.fetch_url.requests.get", return_value=redirect) as get:
            out = fetch_url.invoke({"url": "https://8.8.8.8/start"})

        self.assertEqual(out, BLOCKED_URL_MESSAGE)
        get.assert_called_once()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
