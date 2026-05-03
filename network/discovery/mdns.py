"""
D.I.M — network/discovery/mdns.py
mDNS service announcement and peer discovery via Zeroconf.

Service type : _dim._tcp.local.
Each DIM instance announces itself with:
  - name      : "DIM-{hostname}-{port}._dim._tcp.local."
  - port      : HTTP port (default 5001)
  - properties: role, version, project_name

Peers discovered on the LAN are stored in a registry and
callbacks are fired on join / leave.
"""
from __future__ import annotations

import logging
import socket
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

log = logging.getLogger("dim.mdns")

try:
    from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf, ServiceListener
    from zeroconf import IPVersion
    _ZEROCONF_OK = True
except ImportError:
    _ZEROCONF_OK = False


# ── Constants ─────────────────────────────────────────────────────────────────

SERVICE_TYPE = "_dim._tcp.local."
DIM_VERSION  = "0.5.0"


# ── Peer model ────────────────────────────────────────────────────────────────

@dataclass
class DimPeer:
    name:         str
    host:         str        # hostname or IP
    port:         int
    role:         str  = "slave"   # "master" | "slave"
    project_name: str  = ""
    version:      str  = ""
    addresses:    list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        return f"http://{self.host}:{self.port}"   # SocketIO same port

    def __str__(self) -> str:
        return f"{self.name}  {self.host}:{self.port}  [{self.role}]"


# ── Callbacks ─────────────────────────────────────────────────────────────────

PeerCallback = Callable[[DimPeer], None]


# ── Listener ─────────────────────────────────────────────────────────────────

class _DimListener:
    """Zeroconf service listener — fires callbacks on add/remove."""

    def __init__(
        self,
        zc: "Zeroconf",
        on_add:    PeerCallback,
        on_remove: PeerCallback,
        own_name:  str,
    ) -> None:
        self._zc        = zc
        self._on_add    = on_add
        self._on_remove = on_remove
        self._own_name  = own_name

    def add_service(self, zc: "Zeroconf", type_: str, name: str) -> None:
        peer = self._resolve(zc, type_, name)
        if peer:
            self._on_add(peer)

    def update_service(self, zc: "Zeroconf", type_: str, name: str) -> None:
        peer = self._resolve(zc, type_, name)
        if peer:
            self._on_add(peer)

    def remove_service(self, zc: "Zeroconf", type_: str, name: str) -> None:
        short = name.replace(f".{type_}", "").replace(f".{SERVICE_TYPE}", "")
        self._on_remove(DimPeer(name=short, host="", port=0))

    def _resolve(self, zc: "Zeroconf", type_: str, name: str) -> Optional[DimPeer]:
        # Skip own service
        if name == self._own_name:
            return None
        info = zc.get_service_info(type_, name)
        if not info:
            return None
        props = {
            k.decode() if isinstance(k, bytes) else k:
            v.decode() if isinstance(v, bytes) else v
            for k, v in (info.properties or {}).items()
        }
        addresses = [socket.inet_ntoa(a) for a in info.addresses]
        host = addresses[0] if addresses else info.server or ""
        short = name.replace(f".{SERVICE_TYPE}", "")
        return DimPeer(
            name         = short,
            host         = host,
            port         = info.port,
            role         = props.get("role", "slave"),
            project_name = props.get("project", ""),
            version      = props.get("version", ""),
            addresses    = addresses,
        )


# ── MdnsAnnouncer ─────────────────────────────────────────────────────────────

class MdnsAnnouncer:
    """
    Announces this DIM instance on the LAN and discovers peers.

    Usage:
        ann = MdnsAnnouncer(port=5001, role="master")
        ann.on_peer_added(lambda p: print("found", p))
        ann.on_peer_removed(lambda p: print("gone", p))
        ann.start()
        # later:
        ann.stop()
    """

    def __init__(
        self,
        port:         int  = 5001,
        role:         str  = "slave",
        project_name: str  = "",
        hostname:     str  | None = None,
    ) -> None:
        self._port         = port
        self._role         = role
        self._project_name = project_name
        self._hostname     = hostname or socket.gethostname()
        self._zc:     Optional["Zeroconf"]      = None
        self._info:   Optional["ServiceInfo"]   = None
        self._browser: Optional["ServiceBrowser"] = None
        self._peers:   dict[str, DimPeer]       = {}
        self._lock     = threading.Lock()
        self._add_cbs:    list[PeerCallback] = []
        self._remove_cbs: list[PeerCallback] = []

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def on_peer_added(self, cb: PeerCallback) -> None:
        self._add_cbs.append(cb)

    def on_peer_removed(self, cb: PeerCallback) -> None:
        self._remove_cbs.append(cb)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if not _ZEROCONF_OK:
            log.warning("zeroconf not installed — mDNS unavailable")
            return

        local_ip = self._get_local_ip()
        service_name = f"DIM-{self._hostname}-{self._port}.{SERVICE_TYPE}"

        self._info = ServiceInfo(
            SERVICE_TYPE,
            service_name,
            addresses=[socket.inet_aton(local_ip)],
            port=self._port,
            properties={
                "role":    self._role,
                "project": self._project_name,
                "version": DIM_VERSION,
                "host":    self._hostname,
            },
            server=f"{self._hostname}.local.",
        )

        self._zc = Zeroconf()
        self._zc.register_service(self._info)

        listener = _DimListener(
            zc        = self._zc,
            on_add    = self._peer_added,
            on_remove = self._peer_removed,
            own_name  = service_name,
        )
        self._browser = ServiceBrowser(self._zc, SERVICE_TYPE, listener)
        log.info("mDNS: announced %s on %s:%d", service_name, local_ip, self._port)

    def stop(self) -> None:
        if self._zc:
            try:
                if self._info:
                    self._zc.unregister_service(self._info)
                self._zc.close()
            except Exception:
                pass
            self._zc = None

    def update_project(self, project_name: str) -> None:
        self._project_name = project_name
        if self._zc and self._info:
            props = dict(self._info.properties)
            props[b"project"] = project_name.encode()
            try:
                self._zc.update_service(self._info)
            except Exception:
                pass

    def set_role(self, role: str) -> None:
        self._role = role

    # ── Peer registry ─────────────────────────────────────────────────────────

    def get_peers(self) -> list[DimPeer]:
        with self._lock:
            return list(self._peers.values())

    def get_peer(self, name: str) -> Optional[DimPeer]:
        with self._lock:
            return self._peers.get(name)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _peer_added(self, peer: DimPeer) -> None:
        with self._lock:
            self._peers[peer.name] = peer
        log.info("mDNS peer added: %s", peer)
        for cb in self._add_cbs:
            try:
                cb(peer)
            except Exception:
                pass

    def _peer_removed(self, peer: DimPeer) -> None:
        with self._lock:
            self._peers.pop(peer.name, None)
        log.info("mDNS peer removed: %s", peer.name)
        for cb in self._remove_cbs:
            try:
                cb(peer)
            except Exception:
                pass

    def _get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"


# ── Module-level singleton ─────────────────────────────────────────────────────

_announcer: Optional[MdnsAnnouncer] = None


def get_announcer() -> MdnsAnnouncer:
    global _announcer
    if _announcer is None:
        _announcer = MdnsAnnouncer()
    return _announcer


def is_available() -> bool:
    return _ZEROCONF_OK
