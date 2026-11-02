"""Local development boundary shared by simulated routes.

Never trust a Host or X-Forwarded-For header as proof of client identity.
This does not replace production authentication, proxy policy or RBAC.
"""
from ipaddress import ip_address

from fastapi import Request


def is_local_test_client(request: Request) -> bool:
    """Allow actual TCP loopback or Starlette's in-process TestClient only."""
    if request.client is None:
        return False
    host = request.client.host
    if host == "testclient":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False
