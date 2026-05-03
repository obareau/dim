/**
 * D.I.M — performance.js
 * TUI-style performance view.
 *
 * Layout per lane:
 *   [M.01 LABEL    BADGE]   ← done rows (dimmed)
 *   [M.03 CURRENT  BADGE]   ← current row (highlighted, color border)
 *   [M.04 NEXT     BADGE]   ← next (slightly dim)
 *   [M.05 …             ]   ← upcoming (very dim)
 *
 * The cue list auto-scrolls to keep the active cue visible.
 * State arrives via SocketIO `state_update` at ~20 Hz.
 */

"use strict";

// ── DOM helpers ───────────────────────────────────────────────────────────────
// Must come first — used by setTheme IIFE below.

const el      = id  => document.getElementById(id);
const setText = (id, t) => { const e = el(id); if (e && e.textContent !== String(t)) e.textContent = t; };

// ── Theme ─────────────────────────────────────────────────────────────────────

function setTheme(name) {
  document.body.dataset.theme = name || 'default';
  localStorage.setItem('dim-theme', name);
  const sel = el('pf-theme-select');
  if (sel) sel.value = name;
}

(function initTheme() {
  const saved = localStorage.getItem('dim-theme') || 'default';
  setTheme(saved);
})();

// ── State cache ───────────────────────────────────────────────────────────────

let _state    = null;
let _playing  = false;

// Per-lane cue list: { laneId → [{ id, label, badge, index }] }
// Populated once per project load, updated on section change.
const _laneQueues = {};

// ── Status bar feedback ───────────────────────────────────────────────────────

let _cmdTimer = null;
function showCmd(msg, ttl = 2500) {
  const e = el('pf-footer-cmd');
  if (!e) return;
  e.textContent = msg;
  clearTimeout(_cmdTimer);
  _cmdTimer = setTimeout(() => { e.textContent = ''; }, ttl);
}

// ── Transport ─────────────────────────────────────────────────────────────────

function transport(action) {
  socket.emit('transport', { action });
  const labels = { play: '▶ PLAY', stop: '⏹ STOP', rewind: '⏮ REWIND', toggle: '' };
  if (action !== 'toggle') showCmd(labels[action] || action.toUpperCase());
}

function setTempo(bpm) {
  socket.emit('set_tempo', { bpm });
  showCmd(`TEMPO → ${bpm.toFixed(1)} BPM`);
}

// ── SocketIO events ───────────────────────────────────────────────────────────

socket.on('connect', () => {
  el('pf-live').textContent = '●';
  el('pf-live').classList.add('live');
});
socket.on('disconnect', () => {
  el('pf-live').textContent = '○';
  el('pf-live').classList.remove('live');
});

socket.on('state_update', function (state) {
  _state = state;
  if (!state.loaded) return;

  updateHeader(state);
  updateSyncBadge(state);

  if (state.lanes) {
    Object.values(state.lanes).forEach(lane => updateLane(lane, state));
  }

  // Refresh focus prompt if the focused lane just started waiting
  if (_focusedLane >= 0) {
    const lanes = getLaneMeta();
    const fl    = lanes[_focusedLane];
    if (fl?.waiting) {
      // Brief pulse in footer to alert operator
      const cmd = el('pf-footer-cmd');
      if (cmd && !cmd.textContent.includes('WAITING')) {
        showCmd(`⊙ LANE WAITING — ↵ ADVANCE`, 5000);
      }
    }
  }
});

socket.on('transport_state', function (data) {
  _playing = data.playing;
  refreshPlayBtn();
  if (data.playing) showCmd('▶ PLAYING');
});

// ── Header update ─────────────────────────────────────────────────────────────

function updateHeader(state) {
  // Tempo
  const bpm = state.tempo_bpm;
  const bpmEl = el('pf-tempo');
  if (bpmEl && bpmEl.textContent !== bpm.toFixed(1)) bpmEl.textContent = bpm.toFixed(1);

  // Bar / beat
  setText('pf-bar',  String(state.bar).padStart(2, '0'));
  setText('pf-beat', state.beat_in_bar);

  // Segmented measure bar (16 segments)
  const progress = state.beat_progress || 0;
  const pct      = Math.round(progress * 100);
  const segsOn   = Math.round(progress * 16);
  const segBar   = el('pf-seg-bar');
  if (segBar) {
    segBar.querySelectorAll('.pf-seg').forEach((seg, i) => {
      seg.classList.toggle('on', i < segsOn);
    });
  }
  setText('pf-measure-pct', pct + '%');

  // Elapsed
  setText('pf-elapsed', state.elapsed_fmt || '0:00');

  // Play button
  if (state.playing !== _playing) {
    _playing = state.playing;
    refreshPlayBtn();
  }

  // Status badge
  const sb = el('pf-status-badge');
  if (sb) {
    const anyManual = state.lanes &&
      Object.values(state.lanes).some(l => l.waiting_manual);
    if (anyManual) {
      sb.textContent = 'WAITING';
      sb.className   = 'pf-badge pf-badge-status waiting-manual';
    } else if (state.playing) {
      sb.textContent = 'PLAYING';
      sb.className   = 'pf-badge pf-badge-status playing';
    } else {
      sb.textContent = 'STOPPED';
      sb.className   = 'pf-badge pf-badge-status';
    }
  }
}

function refreshPlayBtn() {
  const btn = el('pf-btn-play');
  if (!btn) return;
  btn.textContent = _playing ? '⏸' : '▶';
  btn.classList.toggle('playing', _playing);
}

function updateSyncBadge(state) {
  // We don't have sync source in state_update yet — poll /api/sync/status
  // For now just show LINK if tempo is being driven externally.
  // TODO: wire sync source into state_update in engine.py
}

// ── Lane update ───────────────────────────────────────────────────────────────

function updateLane(lane, state) {
  const laneEl = el('lane-' + lane.id);
  if (!laneEl) return;

  laneEl.classList.toggle('lane-ended',  !!lane.ended);
  laneEl.classList.toggle('lane-waiting', !!lane.waiting_manual);

  // Section / pass
  setText('lsec-'  + lane.id, lane.section_name ? lane.section_name.toUpperCase() : '');
  setText('lpass-' + lane.id, lane.section_pass > 0 ? `×${lane.section_pass}` : '');

  // Cue list
  renderCueList(lane);

  // Footer — segmented progress + bars label
  const barsEl = el('lbars-' + lane.id);
  const waitEl = el('lwait-' + lane.id);
  const segsEl = el('lsegs-' + lane.id);

  if (lane.ended) {
    if (barsEl) barsEl.textContent = 'END';
    if (waitEl) waitEl.textContent = '';
    if (segsEl) segsEl.querySelectorAll('.pf-lane-seg').forEach(s => s.classList.remove('on'));
  } else if (lane.waiting_manual) {
    if (barsEl) barsEl.textContent = '';
    if (waitEl) waitEl.textContent = '⊙ MANUAL  ↵';
    // Pulse all segments when waiting
    if (segsEl) segsEl.querySelectorAll('.pf-lane-seg').forEach(s => s.classList.add('on'));
  } else {
    const bars    = lane.bars_remaining || 0;
    const maxBars = lane.cue?.duration_bars || 8;
    const ratio   = maxBars > 0 ? Math.min(1, bars / maxBars) : 0;
    const segsOn  = Math.round(ratio * 8);
    if (barsEl) barsEl.textContent = bars > 0 ? bars.toFixed(1) + ' br' : '';
    if (waitEl) waitEl.textContent = '';
    if (segsEl) segsEl.querySelectorAll('.pf-lane-seg').forEach((s, i) => {
      s.classList.toggle('on', i < segsOn);
    });
  }
}

// ── Cue list rendering ────────────────────────────────────────────────────────

/*
 * Build or refresh the ordered cue list for a lane.
 * State gives us: cue (current), prev_cue, next_cue, plus cue_loop_remaining.
 * We reconstruct a window of rows: done | CURRENT | next | upcoming.
 *
 * Because the engine only gives us prev/current/next (not the full queue),
 * we maintain a lightweight history per lane and scroll the visible window.
 */

const _laneHistory  = {};   // laneId → { sectionId, rows: [{id, label, badge}], curIdx }
const _fetchingSection = {}; // laneId → sectionId being fetched (dedup)

function renderCueList(lane) {
  const listEl = el('lcues-' + lane.id);
  if (!listEl) return;

  const hist = _laneHistory[lane.id] || { sectionId: null, rows: [], curIdx: -1 };

  // Section changed → reset history and fetch full cue queue
  if (hist.sectionId !== lane.section_id) {
    hist.sectionId = lane.section_id;
    hist.rows      = [];
    hist.curIdx    = -1;
    // Fetch full queue for this section (async, fills in behind the live updates)
    if (lane.section_id && _fetchingSection[lane.id] !== lane.section_id) {
      _fetchingSection[lane.id] = lane.section_id;
      fetch(`/api/section/${lane.id}/${lane.section_id}/cues`)
        .then(r => r.json())
        .then(cues => {
          const h = _laneHistory[lane.id];
          // Only apply if we're still on the same section
          if (h && h.sectionId === lane.section_id && cues.length > 0) {
            h.rows = cues.map(c => ({ id: c.id, label: c.label, badge: c.badge }));
            // Re-locate current cue index
            if (lane.cue) {
              const idx = h.rows.findIndex(r => r.id === lane.cue.id);
              if (idx !== -1) h.curIdx = idx;
            }
          }
        })
        .catch(() => {});
    }
  }

  // Build/extend row list from what the engine tells us
  const cur  = lane.cue;
  const next = lane.next_cue;
  const prev = lane.prev_cue;

  if (!cur && !lane.ended) {
    listEl.innerHTML = '<div class="pf-cue-placeholder">—</div>';
    _laneHistory[lane.id] = hist;
    return;
  }

  if (lane.ended) {
    // Show END marker
    listEl.innerHTML = '<div class="pf-cue-row is-current"><span class="pf-ci">■</span><span class="pf-cl">END</span></div>';
    _laneHistory[lane.id] = hist;
    return;
  }

  // Ensure current cue is in rows
  const curId = cur?.id;
  let curIdx  = hist.rows.findIndex(r => r.id === curId);

  if (curIdx === -1) {
    // Insert: if we have prev and prev is last in history, append current after it
    const prevId = prev?.id;
    const prevIdx = prevId ? hist.rows.findIndex(r => r.id === prevId) : -1;

    if (prevIdx !== -1) {
      // Insert after prev
      hist.rows.splice(prevIdx + 1, 0, { id: curId, label: cur.label, badge: cur.badge });
      curIdx = prevIdx + 1;
    } else {
      // Cold start or big jump: rebuild with what we know
      const newRows = [];
      if (prev) newRows.push({ id: prev.id, label: prev.label, badge: prev.badge });
      if (cur)  newRows.push({ id: curId,   label: cur.label,  badge: cur.badge  });
      if (next) newRows.push({ id: next.id, label: next.label, badge: next.badge });
      hist.rows  = newRows;
      curIdx     = prev ? 1 : 0;
    }
  } else {
    // Update badge (loop count etc. may change)
    if (cur) hist.rows[curIdx] = { id: curId, label: cur.label, badge: cur.badge };
  }

  // Ensure next cue is after current in rows
  if (next) {
    const nextId  = next.id;
    const nextIdx = hist.rows.findIndex(r => r.id === nextId);
    if (nextIdx === -1) {
      hist.rows.splice(curIdx + 1, 0, { id: nextId, label: next.label, badge: next.badge });
    }
  }

  hist.curIdx = curIdx;
  _laneHistory[lane.id] = hist;

  // Render rows
  const MAX_VISIBLE = 20;
  // Show a window: [curIdx-3 … curIdx+MAX_VISIBLE]
  const startIdx = Math.max(0, curIdx - 3);
  const endIdx   = Math.min(hist.rows.length, startIdx + MAX_VISIBLE);
  const window   = hist.rows.slice(startIdx, endIdx);

  // Build HTML
  let html = '';
  window.forEach((row, wi) => {
    const absIdx  = startIdx + wi;
    const isCur   = absIdx === curIdx;
    const isNext  = absIdx === curIdx + 1;
    const isDone  = absIdx < curIdx;
    const isManual = isCur && lane.waiting_manual;

    let cls = 'pf-cue-row';
    if (isManual) cls += ' is-manual';
    else if (isCur)  cls += ' is-current';
    else if (isNext) cls += ' is-next';
    else if (isDone) cls += ' is-done';

    const idxLabel = `M.${String(absIdx + 1).padStart(2, '0')}`;
    const badge    = row.badge ? escHtml(row.badge) : '';
    const label    = row.label ? escHtml(row.label) : '—';

    html += `<div class="${cls}">` +
      `<span class="pf-ci">${idxLabel}</span>` +
      `<span class="pf-cl">${label}</span>` +
      (badge ? `<span class="pf-cb">${badge}</span>` : '') +
      `</div>`;
  });

  if (html !== listEl.innerHTML) {
    listEl.innerHTML = html;
  }

  // Scroll active row into view
  const curRow = listEl.querySelector('.is-current, .is-manual');
  if (curRow) {
    curRow.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ── Sync status poll ──────────────────────────────────────────────────────────

async function pollSyncStatus() {
  try {
    const r = await fetch('/api/sync/status');
    if (!r.ok) return;
    const data = await r.json();
    const badge = el('pf-sync-badge');
    if (!badge) return;

    const src = data.active_source || 'internal';
    const map = {
      link:     ['SYNC: LINK',     'link'],
      midi:     ['SYNC: MIDI',     'midi'],
      osc:      ['SYNC: OSC',      'osc'],
      internal: ['SYNC: INTERNAL', ''],
    };
    const [label, cls] = map[src] || map.internal;
    badge.textContent = label;
    badge.className   = 'pf-badge pf-badge-sync' + (cls ? ' active ' + cls : '');
  } catch (_) { /* offline */ }
}

// Poll sync status every 3 s (not time-critical)
pollSyncStatus();
setInterval(pollSyncStatus, 3000);

// ── Manual advance ────────────────────────────────────────────────────────────

// Focused lane index (0-based), or -1 = none.
let _focusedLane = -1;

function getLaneMeta() {
  // Returns ordered array of { el, id, waiting } from current state
  return Array.from(document.querySelectorAll('.pf-lane')).map(laneEl => {
    const id = laneEl.dataset.laneId;
    const laneState = _state?.lanes?.[id];
    return { el: laneEl, id, waiting: !!(laneState?.waiting_manual) };
  });
}

function focusLane(n /* 1-based */) {
  const lanes = getLaneMeta();
  const idx   = n - 1;
  _focusedLane = (idx >= 0 && idx < lanes.length) ? idx : -1;
  lanes.forEach((l, i) => l.el.classList.toggle('pf-lane--focused', i === _focusedLane));
  if (_focusedLane >= 0) {
    const l = lanes[_focusedLane];
    showCmd(`⊡ LANE ${n}${l.waiting ? '  ↵ ADVANCE' : ''}`);
  }
}

function advanceLane(laneId) {
  socket.emit('manual_advance', { lane_id: laneId });
  showCmd(`⊙ ADVANCE → ${laneId}`);
}

function advanceAllWaiting() {
  const waiting = getLaneMeta().filter(l => l.waiting);
  if (waiting.length === 0) { showCmd('NO LANE WAITING'); return; }
  waiting.forEach(l => socket.emit('manual_advance', { lane_id: l.id }));
  showCmd(`⊙ ADVANCE ALL (${waiting.length})`);
}

// Cycle through the theme list
const _themes = ['default','gruvbox','nord','dracula','solarized','monokai',
                 'onedark','catppuccin','tokyo','iceberg','tango','light','astro'];

function cycleTheme() {
  const current = document.body.dataset.theme || 'default';
  const idx  = _themes.indexOf(current);
  const next = _themes[(idx + 1) % _themes.length];
  setTheme(next);
  showCmd(`THEME → ${next.toUpperCase()}`);
}

// ── Keyboard shortcuts ────────────────────────────────────────────────────────

document.addEventListener('keydown', function (e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' ||
      e.target.tagName === 'SELECT') return;

  switch (e.code) {

    // ── Transport ──
    case 'Space':
      e.preventDefault();
      transport('toggle');
      break;

    case 'KeyR':
      transport('rewind');
      break;

    case 'KeyS':
      transport('stop');
      break;

    // ── Navigation ──
    case 'KeyE':
      window.location.href = '/editor';
      break;

    // ── Tempo ──
    case 'ArrowUp':
      e.preventDefault();
      if (_state?.tempo_bpm) {
        const bpm = Math.min(300, (_state.tempo_bpm || 120) + (e.shiftKey ? 5 : 1));
        setTempo(bpm);
      }
      break;

    case 'ArrowDown':
      e.preventDefault();
      if (_state?.tempo_bpm) {
        const bpm = Math.max(20, (_state.tempo_bpm || 120) - (e.shiftKey ? 5 : 1));
        setTempo(bpm);
      }
      break;

    // ── Manual advance — focused lane ──
    case 'Enter':
    case 'NumpadEnter': {
      e.preventDefault();
      const lanes = getLaneMeta();
      if (_focusedLane >= 0 && lanes[_focusedLane]?.waiting) {
        advanceLane(lanes[_focusedLane].id);
      } else if (_focusedLane >= 0) {
        showCmd('LANE NOT WAITING');
      } else {
        // No focus → advance first waiting lane
        const w = lanes.find(l => l.waiting);
        if (w) advanceLane(w.id);
        else showCmd('NO LANE WAITING');
      }
      break;
    }

    // ── Manual advance — ALL waiting lanes ──
    case 'KeyA':
      e.preventDefault();
      advanceAllWaiting();
      break;

    // ── Theme cycle ──
    case 'KeyT':
      cycleTheme();
      break;

    // ── Lane focus 1–9 ──
    default:
      if (e.code.startsWith('Digit') && !e.ctrlKey && !e.metaKey) {
        const n = parseInt(e.key);
        if (n >= 1 && n <= 9) focusLane(n);
      }
      // 0 = deselect focus
      if (e.code === 'Digit0') {
        _focusedLane = -1;
        document.querySelectorAll('.pf-lane').forEach(l => l.classList.remove('pf-lane--focused'));
        showCmd('FOCUS CLEARED');
      }
  }
});
