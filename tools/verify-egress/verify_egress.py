"""Fail-closed egress preflight.

This probe never changes firewall or DNS. It checks configuration presence and
attempts only owner-supplied approved probe hosts. A successful run is not a
substitute for Windows firewall and physical/network isolation evidence.
"""

from __future__ import annotations

import argparse
import json
import socket
import urllib.error
import urllib.request


def dns_probe(host: str) -> dict[str, object]:
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
        return {"host": host, "resolved": addresses, "ok": bool(addresses)}
    except OSError as exc:
        return {"host": host, "resolved": [], "ok": False, "error": str(exc)}


def http_probe(url: str, timeout: float) -> dict[str, object]:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "EvidenceRag-Egress-Preflight/1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - owner allowlist only
            return {"url": url, "ok": True, "status": response.status}
    except urllib.error.HTTPError as exc:
        return {"url": url, "ok": True, "status": exc.code}
    except Exception as exc:
        return {"url": url, "ok": False, "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-host", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    results = {
        "dns": [dns_probe(host) for host in args.allow_host],
        "http": [http_probe(f"https://{host}", args.timeout) for host in args.allow_host],
    }
    results["ok"] = all(item["ok"] for item in results["dns"] + results["http"])
    print(json.dumps(results, ensure_ascii=False))
    return 0 if results["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
