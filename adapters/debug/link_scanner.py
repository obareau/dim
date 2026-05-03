"""
D.I.M — adapters/debug/link_scanner.py
Scan local network for Ableton Link peers.

Two parallel approaches:
  1. Multicast sniffer  → source IPs from 224.76.78.75:20808
  2. aalink session     → official peer count + tempo

The Link (ILES) protocol doesn't expose device names publicly,
but IP + reverse DNS gives enough info for a debug panel.
"""
from __future__ import annotations

import asyncio
import socket
import struct
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

LINK_MCAST_GRP  = "224.76.78.75"
LINK_MCAST_PORT = 20808
SCAN_DURATION   = 5.0


@dataclass
class LinkPeer:
    ip:           str
    hostname:     str   = ""
    first_seen:   float = field(default_factory=time.monotonic)
    last_seen:    float = field(default_factory=time.monotonic)
    packet_count: int   = 0

    def touch(self) -> None:
        self.last_seen = time.monotonic()
        self.packet_count += 1


def _local_ips() -> list[str]:
    """Return active local IPv4 addresses (excluding loopback)."""
    ips: list[str] = []
    try:
        # Primary IP via UDP trick
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass

    # Also enumerate via getaddrinfo to catch multi-homed hosts
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass

    return ips or ["0.0.0.0"]


def _make_mcast_socket(local_ips: list[str]) -> Optional[socket.socket]:
    """Create and join the Link multicast group. Returns None on failure."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        sock.bind(("", LINK_MCAST_PORT))

        joined = 0
        for ip in local_ips:
            try:
                mreq = struct.pack("4s4s",
                                   socket.inet_aton(LINK_MCAST_GRP),
                                   socket.inet_aton(ip))
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                joined += 1
            except OSError:
                pass

        if joined == 0:
            sock.close()
            return None

        sock.setblocking(False)
        return sock

    except OSError:
        sock.close()
        return None


async def _resolve_hostname(ip: str) -> str:
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, lambda: socket.gethostbyaddr(ip)[0]),
            timeout=2.0
        )
    except Exception:
        return ""


async def scan_peers(
    duration: float = SCAN_DURATION,
    on_peer: Callable[[LinkPeer], None] | None = None,
    on_count: Callable[[int], None] | None = None,
) -> tuple[list[LinkPeer], int, str | None]:
    """
    Scan for Link peers for `duration` seconds.

    Returns:
        (peers, sdk_peer_count, error_msg)
        error_msg is None on success, a string describing the problem otherwise.
    """
    local_ips = _local_ips()
    peers: dict[str, LinkPeer] = {}
    sdk_peer_count = 0
    error_msg = None

    # ── Socket ────────────────────────────────────────────────────────────────
    sock = _make_mcast_socket(local_ips)
    if sock is None:
        error_msg = "Could not bind multicast socket (port 20808 in use?)"

    # ── aalink session ────────────────────────────────────────────────────────
    link = None
    try:
        import aalink
        link = aalink.Link(120.0)
        link.enabled = True

        def _on_peers(n: int) -> None:
            nonlocal sdk_peer_count
            sdk_peer_count = n
            if on_count:
                on_count(n)

        link.set_num_peers_callback(_on_peers)
    except Exception as e:
        if error_msg is None:
            error_msg = f"aalink error: {e}"

    # ── Collect ───────────────────────────────────────────────────────────────
    deadline = asyncio.get_event_loop().time() + duration

    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.05)

        if sock is not None:
            try:
                while True:
                    data, addr = sock.recvfrom(4096)
                    src_ip = addr[0]
                    if src_ip in local_ips:
                        continue
                    if src_ip not in peers:
                        peers[src_ip] = LinkPeer(ip=src_ip)
                    else:
                        peers[src_ip].touch()
            except BlockingIOError:
                pass

    # ── Cleanup ───────────────────────────────────────────────────────────────
    if sock is not None:
        sock.close()

    if link is not None:
        # Read count BEFORE disabling
        sdk_peer_count = max(sdk_peer_count, link.num_peers)
        try:
            link.enabled = False
        except Exception:
            pass

    # ── Reverse DNS (after collection to avoid blocking the loop) ─────────────
    dns_tasks = [_resolve_hostname(ip) for ip in peers]
    hostnames = await asyncio.gather(*dns_tasks, return_exceptions=True)
    for peer, hostname in zip(peers.values(), hostnames):
        if isinstance(hostname, str):
            peer.hostname = hostname
        if on_peer:
            on_peer(peer)

    return list(peers.values()), sdk_peer_count, error_msg
