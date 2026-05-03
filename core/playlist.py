"""
D.I.M — core/playlist.py
Cue queue construction for a section pass.
Pure function: build_cue_queue(section, pass_index) → list[Cue].
"""
from __future__ import annotations

from core.models import Section, Cue


def build_cue_queue(section: Section, pass_index: int = 0) -> list[Cue]:
    """
    Build the ordered list of enabled cues to play for a given section pass.

    Args:
        section:    The section to build the queue for.
        pass_index: 0-based pass number through this section.
                    Affects "nth" and "ratio" modes (though ratio is pass-independent).

    Returns:
        Ordered list of Cue objects (enabled only, sorted by order_index).
        May be empty.

    Playlist modes:
        "all"    — all enabled cues in order_index order
        "nth"    — 1 out of nth cues, cycling by pass_index
                   (nth=2, pass 0 → cues at even indices; pass 1 → cues at odd indices)
        "ratio"  — first M cues out of every N  (ratio="3:4" → i%4 < 3)
        "custom" — explicit list of order_index values
    """
    enabled = sorted(
        [c for c in section.cues if c.enabled],
        key=lambda c: c.order_index,
    )

    mode = section.playlist.mode

    if mode == "all":
        return list(enabled)

    if mode == "nth":
        nth = max(1, section.playlist.nth or 1)
        # Distribute cues across passes: pass P gets cues at indices where i % nth == P % nth
        return [c for i, c in enumerate(enabled) if i % nth == pass_index % nth]

    if mode == "ratio":
        ratio_str = section.playlist.ratio or "1:1"
        try:
            m_str, n_str = ratio_str.split(":")
            m, n = int(m_str), int(n_str)
        except (ValueError, AttributeError):
            return list(enabled)
        if n <= 0:
            return list(enabled)
        return [c for i, c in enumerate(enabled) if i % n < m]

    if mode == "custom":
        if section.playlist.custom_order:
            return [
                enabled[i]
                for i in section.playlist.custom_order
                if 0 <= i < len(enabled)
            ]
        return list(enabled)

    # Unknown mode → all
    return list(enabled)
