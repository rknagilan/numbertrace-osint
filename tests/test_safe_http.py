import httpx
import pytest

from numbertrace.net.safe_http import SafeHTTPClient, UnsafeURLError, check_url

ALLOW = ["api.search.brave.com"]


def public(host):
    return ["93.184.216.34"]


@pytest.mark.parametrize(
    "url,msg",
    [
        ("http://api.search.brave.com/x", "https"),
        ("file:///etc/passwd", "https"),
        ("https://127.0.0.1/", "literal IP"),
        ("https://[::1]/", "literal IP"),
        ("https://169.254.169.254/latest/meta-data", "literal IP"),
        ("https://user:pw@api.search.brave.com/", "credentials"),
        ("https://api.search.brave.com:8443/", "ports"),
        ("https://evil.example/", "allowlist"),
        ("https://api.search.brave.com.evil.example/", "allowlist"),
    ],
)
def test_ssrf_url_policy(url, msg):
    with pytest.raises(UnsafeURLError, match=msg):
        check_url(url, ALLOW, public)


@pytest.mark.parametrize(
    "addr",
    [
        "10.0.0.5",
        "192.168.1.1",
        "127.0.0.1",
        "169.254.169.254",
        "::1",
        "::ffff:10.0.0.1",
        "fd00::1",
    ],
)
def test_dns_rebinding_to_private_ip_blocked(addr):
    with pytest.raises(UnsafeURLError, match="non-public"):
        check_url("https://api.search.brave.com/x", ALLOW, lambda h: [addr])


def test_dns_failure_is_reported():
    def boom(h):
        raise OSError("nope")

    with pytest.raises(UnsafeURLError, match="DNS"):
        check_url("https://api.search.brave.com/x", ALLOW, boom)


def test_public_host_allowed():
    assert check_url("https://API.search.brave.com/x", ALLOW, public) == "api.search.brave.com"


async def test_redirects_not_followed():
    def handler(req):
        return httpx.Response(302, headers={"Location": "https://169.254.169.254/"})

    http = SafeHTTPClient(transport=httpx.MockTransport(handler), resolver=public)
    with pytest.raises(UnsafeURLError, match="redirect"):
        await http.get_json("https://api.search.brave.com/x", allowed_hosts=ALLOW)
    await http.aclose()


async def test_bounded_retries_on_503():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] == 1 else httpx.Response(200, json={"ok": True})

    http = SafeHTTPClient(transport=httpx.MockTransport(handler), resolver=public, retries=1)
    assert await http.get_json("https://api.search.brave.com/x", allowed_hosts=ALLOW) == {"ok": True}
    assert calls["n"] == 2
    await http.aclose()


async def test_retries_are_bounded():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503)

    http = SafeHTTPClient(transport=httpx.MockTransport(handler), resolver=public, retries=10)
    with pytest.raises(httpx.HTTPStatusError):
        await http.get_json("https://api.search.brave.com/x", allowed_hosts=ALLOW)
    assert calls["n"] == 4  # retries capped at 3
    await http.aclose()


async def test_oversized_response_rejected():
    def handler(req):
        return httpx.Response(200, content=b'{"a":"' + b"x" * 5000 + b'"}')

    http = SafeHTTPClient(transport=httpx.MockTransport(handler), resolver=public, max_response_bytes=1000)
    with pytest.raises(ValueError, match="too large"):
        await http.get_json("https://api.search.brave.com/x", allowed_hosts=ALLOW)
    await http.aclose()
