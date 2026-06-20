"""Fetch-URL tool for the Mini-OpenClaw agent.

Wraps ``langchain_community.tools.RequestsGetTool`` and post-processes the
raw HTML response into clean Markdown-style text so the agent receives
something it can actually reason over instead of a wall of tags.

The cleaning pipeline is:

1. Strip ``<script>`` and ``<style>`` elements with BeautifulSoup so their
   inline contents do not leak into the conversion.
2. Convert the remaining HTML to Markdown with ``html2text``, with line
   wrapping disabled so paragraphs stay on a single line.
3. Strip trailing whitespace so the output is tidy.
"""

from __future__ import annotations

import html2text
from bs4 import BeautifulSoup
from langchain_community.tools import RequestsGetTool
from langchain_community.utilities.requests import TextRequestsWrapper
from langchain_core.tools import tool

_REQUESTS_TOOL: RequestsGetTool = RequestsGetTool(
    requests_wrapper=TextRequestsWrapper(),
    allow_dangerous_requests=True,
)

PARSE_FAILURE_MESSAGE: str = (
    "Fetched the page, but could not parse it into readable text. "
    "Please retry with a simpler page or inspect the raw source manually."
)


def _clean_html(raw_html: str) -> str:
    """Strip ``<script>``/``<style>`` and convert the remainder to Markdown."""
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(("script", "style")):
        tag.decompose()
    stripped = str(soup)

    converter = html2text.HTML2Text()
    converter.body_width = 0
    converter.ignore_images = False
    converter.ignore_links = False
    return converter.handle(stripped).rstrip()


@tool("fetch_url")
def fetch_url(url: str) -> str:
    """Fetch a URL and return its body as cleaned Markdown text.

    ``<script>`` and ``<style>`` blocks are removed before conversion so the
    result is suitable for an LLM to read directly.

    Args:
        url: An absolute ``http://`` or ``https://`` URL to GET.

    Returns:
        Markdown-style text representation of the page body.
    """
    raw = _REQUESTS_TOOL.invoke({"url": url})
    if not isinstance(raw, str):
        raw = str(raw)
    try:
        return _clean_html(raw)
    except Exception:
        return PARSE_FAILURE_MESSAGE


__all__ = ["fetch_url", "PARSE_FAILURE_MESSAGE"]
