"""Fetch public web pages for the Mini-OpenClaw agent.

The tool validates every requested URL and redirect target before issuing a
request. This prevents the agent from using a public-web tool to reach local
or private network services that bypass the project filesystem boundary.

The cleaning pipeline is:

1. Strip ``<script>`` and ``<style>`` elements with BeautifulSoup so their
   inline contents do not leak into the conversion.
2. Convert the remaining HTML to Markdown with ``html2text``, with line
   wrapping disabled so paragraphs stay on a single line.
3. Strip trailing whitespace so the output is tidy.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import html2text
import requests
from bs4 import BeautifulSoup
from langchain_core.tools import tool

PARSE_FAILURE_MESSAGE: str = (
    "Fetched the page, but could not parse it into readable text. "
    "Please retry with a simpler page or inspect the raw source manually."
)
FETCH_FAILURE_MESSAGE = "Could not fetch that public URL. Please verify it and try again."
BLOCKED_URL_MESSAGE = "[fetch_url] refused: URLs must resolve only to public HTTP(S) hosts."
REQUEST_TIMEOUT_SECONDS = 10
MAX_REDIRECTS = 3


class UnsafeUrlError(ValueError):
    """Raised when a URL could reach a non-public network address."""


def _resolve_host(hostname: str, port: int) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        return {ipaddress.ip_address(hostname)}
    except ValueError:
        pass
    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError("hostname could not be resolved") from exc
    return {ipaddress.ip_address(address[4][0]) for address in addresses}


def _validate_public_url(raw_url: str) -> str:
    parsed = urlsplit(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("only absolute HTTP(S) URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("credential-bearing URLs are not allowed")

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeUrlError("URL port is invalid") from exc
    addresses = _resolve_host(parsed.hostname, port)
    if not addresses or any(not address.is_global for address in addresses):
        raise UnsafeUrlError("URL resolves to a non-public address")
    return raw_url


def _fetch_text(url: str) -> str:
    current_url = _validate_public_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        response = requests.get(
            current_url,
            allow_redirects=False,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if 300 <= response.status_code < 400:
            location = response.headers.get("Location")
            if not location:
                response.raise_for_status()
                return response.text
            current_url = _validate_public_url(urljoin(current_url, location))
            continue
        response.raise_for_status()
        return response.text
    raise requests.TooManyRedirects("redirect limit exceeded")


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
    try:
        raw = _fetch_text(url)
    except UnsafeUrlError:
        return BLOCKED_URL_MESSAGE
    except requests.RequestException:
        return FETCH_FAILURE_MESSAGE
    try:
        return _clean_html(raw)
    except Exception:
        return PARSE_FAILURE_MESSAGE


__all__ = [
    "BLOCKED_URL_MESSAGE",
    "FETCH_FAILURE_MESSAGE",
    "PARSE_FAILURE_MESSAGE",
    "fetch_url",
]
