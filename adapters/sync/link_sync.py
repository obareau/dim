"""
D.I.M — adapters/sync/link_sync.py
Ableton Link sync source via aalink (https://github.com/artfwo/aalink).

Install:  pip install aalink
Requires: Python 3.9+, macOS/Linux/Windows

aalink API (pybind11, threaded mode):
    link = aalink.Link(bpm)            # join Link session
    link.beat                          # current beat (float)
    link.num_peers                     # number of peers (int)
    link.set_tempo_callback(cb)        # cb(bpm: float)
    link.set_start_stop_callback(cb)   # cb(is_playing: bool)
    link.set_num_peers_callback(cb)    # cb(n: int)

If aalink is not installed, LinkSyncStub is returned by make_link_source()
— the rest of the app works unchanged.
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Optional

from .base import SyncSource, SyncSourceType, SyncState

# ── Try importing aalink ───────────────────────────────────────────────────────

try:
    import aalink as _aalink
    _LINK_AVAILABLE = True
except ImportError:
    _aalink = None
    _LINK_AVAILABLE = False


def is_link_available() -> bool:
    return _LINK_AVAILABLE


# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_QUANTUM = 4.0        # beats per quantum (1 bar at 4/4)
BEAT_POLL_HZ    = 25         # beat position poll rate (background thread)


# ── Ableton Link Source ────────────────────────────────────────────────────────

class LinkSyncSource(SyncSource):
    """
    Ableton Link peer via aalink.
    Joins the Link session on start(), leaves on stop().
    Emits tempo/beat/play callbacks.
    """

    def __init__(self, quantum: float = DEFAULT_QUANTUM) -> None:
        super().__init__()
        self._quantum  = quantum
        self._link     = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running  = False
        self._lock     = threading.Lock()

        # cached state
        self._tempo_bpm   = 120.0
        self._beat_pos    = 0.0
        self._is_playing  = False
        self._peer_count  = 0

    @property
    def source_type(self) -> SyncSourceType:
        return SyncSourceType.ABLETON_LINK

    @property
    def is_available(self) -> bool:
        return _LINK_AVAILABLE and self._link is not None

    @property
    def peer_count(self) -> int:
        with self._lock:
            return self._peer_count

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if not _LINK_AVAILABLE:
            return
        with self._lock:
            bpm = self._tempo_bpm

        self._running = True
        self._thread = threading.Thread(
            target=self._run_async, args=(bpm,), daemon=True, name="dim-link"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)

    def _run_async(self, initial_bpm: float) -> None:
        """Dedicated asyncio event loop in a background thread — required by aalink."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_main(initial_bpm))
        finally:
            self._loop.close()
            self._loop = None

    async def _async_main(self, initial_bpm: float) -> None:
        try:
            self._link = _aalink.Link(initial_bpm)
            self._link.enabled = True
            self._link.start_stop_sync_enabled = True
        except Exception:
            return

        self._link.set_tempo_callback(self._cb_tempo)
        self._link.set_start_stop_callback(self._cb_play)
        self._link.set_num_peers_callback(self._cb_peers)

        interval = 1.0 / BEAT_POLL_HZ
        while self._running:
            await asyncio.sleep(interval)
            if self._link is not None:
                beat = self._link.beat
                with self._lock:
                    self._beat_pos = beat
                self._emit_beat(beat)

    def get_state(self) -> SyncState:
        with self._lock:
            return SyncState(
                source=SyncSourceType.ABLETON_LINK,
                tempo_bpm=self._tempo_bpm,
                beat_position=self._beat_pos,
                is_playing=self._is_playing,
                is_available=_LINK_AVAILABLE and self._link is not None,
            )

    # ── Push to Link ─────────────────────────────────────────────────────────

    def set_tempo(self, bpm: float) -> None:
        """Push a new tempo to the Link session."""
        if self._link is None or self._loop is None:
            return
        try:
            link = self._link
            async def _set():
                if link is not None:
                    await link.sync(link.beat, origin=bpm)
            asyncio.run_coroutine_threadsafe(_set(), self._loop)
        except Exception:
            pass

    def set_playing(self, playing: bool) -> None:
        """Push play/stop to the Link session."""
        if self._link is None or self._loop is None:
            return
        try:
            link = self._link
            async def _set():
                if link is not None:
                    await link.set_is_playing_and_request_beat_at_time(
                        playing,
                        __import__('datetime').timedelta(0),
                        0.0,
                    )
            asyncio.run_coroutine_threadsafe(_set(), self._loop)
        except Exception:
            pass

    # ── Callbacks from aalink ────────────────────────────────────────────────

    def _cb_tempo(self, bpm: float) -> None:
        with self._lock:
            self._tempo_bpm = bpm
        self._emit_tempo(bpm)

    def _cb_play(self, is_playing: bool) -> None:
        with self._lock:
            self._is_playing = is_playing
        self._emit_play(is_playing)

    def _cb_peers(self, n: int) -> None:
        with self._lock:
            self._peer_count = n



# ── Stub ──────────────────────────────────────────────────────────────────────

class LinkSyncStub(SyncSource):
    """No-op stub when aalink is not installed."""

    @property
    def source_type(self) -> SyncSourceType:
        return SyncSourceType.ABLETON_LINK

    @property
    def peer_count(self) -> int:
        return 0

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def get_state(self) -> SyncState:
        return SyncState(
            source=SyncSourceType.ABLETON_LINK,
            tempo_bpm=120.0,
            beat_position=0.0,
            is_playing=False,
            is_available=False,
        )

    def set_tempo(self, bpm: float) -> None:
        pass

    def set_playing(self, playing: bool) -> None:
        pass


def make_link_source(quantum: float = DEFAULT_QUANTUM) -> SyncSource:
    """Factory — returns real LinkSyncSource or stub depending on availability."""
    if _LINK_AVAILABLE:
        return LinkSyncSource(quantum)
    return LinkSyncStub()
