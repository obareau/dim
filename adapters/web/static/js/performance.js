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

  // Section-end instruction badge (what fires when this section finishes)
  const nextEl = el('lnext-' + lane.id);
  if (nextEl) {
    const badge = lane.section_next || '';
    const vetoed = lane.veto_jump && badge.includes('↗');
    nextEl.textContent = badge ? ('→ ' + badge + (vetoed ? ' ✗' : '')) : '';
    // Color-code by instruction type
    nextEl.className = 'pf-lane-next' +
      (vetoed              ? ' jump vetoed' :
       badge.includes('↗') ? ' jump' :
       badge.includes('↺') ? ' loop' :
       badge.includes('⊙') ? ' manual' :
       badge.includes('⤵') ? ' gosub' : '');
  }

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

// ── Lane focus ────────────────────────────────────────────────────────────────

let _focusedLane = -1;

function getLaneMeta() {
  return Array.from(document.querySelectorAll('.pf-lane')).map(laneEl => {
    const id = laneEl.dataset.laneId;
    const ls = _state?.lanes?.[id];
    return {
      el:      laneEl,
      id,
      waiting: !!(ls?.waiting_manual),
      hasJump: !!(ls?.section_next?.includes('↗')),
    };
  });
}

function focusLane(n /* 1-based */) {
  const lanes = getLaneMeta();
  const idx   = n - 1;
  _focusedLane = (idx >= 0 && idx < lanes.length) ? idx : -1;
  lanes.forEach((l, i) => l.el.classList.toggle('pf-lane--focused', i === _focusedLane));
  if (_focusedLane >= 0) {
    const l = lanes[_focusedLane];
    const hint = l.waiting  ? '  ↵ ADVANCE' :
                 l.hasJump  ? '  V VETO JUMP' : '';
    showCmd(`⊡ LANE ${n}${hint}`);
  }
}

function focusRelative(delta) {
  const lanes = getLaneMeta();
  if (!lanes.length) return;
  const next = (_focusedLane + delta + lanes.length) % lanes.length;
  focusLane(next + 1);
}

function clearFocus() {
  _focusedLane = -1;
  document.querySelectorAll('.pf-lane').forEach(l => l.classList.remove('pf-lane--focused'));
  showCmd('FOCUS CLEARED');
}

// ── Manual advance ────────────────────────────────────────────────────────────

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

// ── Veto JUMP ─────────────────────────────────────────────────────────────────

function vetoJump() {
  const lanes = getLaneMeta();
  const target = _focusedLane >= 0 ? lanes[_focusedLane] : lanes.find(l => l.hasJump);
  if (!target) { showCmd('NO JUMP TO VETO'); return; }
  socket.emit('veto_jump', { lane_id: target.id });
  showCmd(`⛔ VETO → ${target.id}`);
}

// ── Tap tempo ─────────────────────────────────────────────────────────────────

const _tapTimes = [];
const TAP_WINDOW = 3000; // ms — reset if gap > 3s
const TAP_MIN    = 2;    // minimum taps before showing BPM
const TAP_APPLY  = 4;    // apply BPM after N taps

function tapTempo() {
  const now = Date.now();
  // Flush old taps
  while (_tapTimes.length && (now - _tapTimes[0]) > TAP_WINDOW) {
    _tapTimes.shift();
  }
  _tapTimes.push(now);

  if (_tapTimes.length < TAP_MIN) {
    showCmd(`TAP (${_tapTimes.length}/4)…`, 3000);
    return;
  }

  // Average interval of last pairs
  const intervals = [];
  for (let i = 1; i < _tapTimes.length; i++) {
    intervals.push(_tapTimes[i] - _tapTimes[i - 1]);
  }
  const avgMs = intervals.reduce((a, b) => a + b, 0) / intervals.length;
  const bpm   = Math.round(60000 / avgMs * 10) / 10;
  const clamped = Math.min(300, Math.max(20, bpm));

  showCmd(`TAP: ${clamped.toFixed(1)} BPM (×${_tapTimes.length})`, 3000);

  if (_tapTimes.length >= TAP_APPLY) {
    setTempo(clamped);
    _tapTimes.length = 0; // reset after applying
  }
}

// ── Zoom ─────────────────────────────────────────────────────────────────────

const _zoomLevels = [0.7, 0.85, 1.0, 1.15, 1.3];
let _zoomIdx = parseInt(localStorage.getItem('pf-zoom') || '2');

function applyZoom(idx) {
  _zoomIdx = Math.max(0, Math.min(_zoomLevels.length - 1, idx));
  localStorage.setItem('pf-zoom', _zoomIdx);
  const scale = _zoomLevels[_zoomIdx];
  const lanesEl = el('pf-lanes');
  if (lanesEl) {
    lanesEl.style.fontSize  = scale + 'em';
    lanesEl.style.transform = _zoomIdx === 2 ? '' : `scale(${scale})`;
    lanesEl.style.transformOrigin = 'top left';
    // Compensate height so footer stays visible
    lanesEl.style.height = _zoomIdx === 2 ? '' : `${100 / scale}%`;
  }
  showCmd(`ZOOM ${Math.round(scale * 100)}%`);
}

function zoomIn()    { applyZoom(_zoomIdx + 1); }
function zoomOut()   { applyZoom(_zoomIdx - 1); }
function zoomReset() { applyZoom(2); }

// ── Time signature ────────────────────────────────────────────────────────────

const _timeSigs = ['4/4', '3/4', '6/8', '5/4', '7/8', '2/4', '12/8'];
let _timeSigIdx = 0;

function initTimeSigIdx() {
  const current = el('pf-ts')?.textContent?.trim() || '4/4';
  _timeSigIdx = Math.max(0, _timeSigs.indexOf(current));
}

function cycleTimeSig(reverse = false) {
  _timeSigIdx = (_timeSigIdx + (reverse ? -1 : 1) + _timeSigs.length) % _timeSigs.length;
  const ts = _timeSigs[_timeSigIdx];
  fetch('/api/transport/time-signature', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ time_signature: ts }),
  });
  showCmd(`TIME SIG → ${ts}`);
}

// ── Theme cycle ───────────────────────────────────────────────────────────────

const _themes = ['default','gruvbox','nord','dracula','solarized','monokai',
                 'onedark','catppuccin','tokyo','iceberg','tango','light','astro'];

function cycleTheme(reverse = false) {
  const current = document.body.dataset.theme || 'default';
  const idx  = _themes.indexOf(current);
  const next = _themes[(idx + (reverse ? -1 : 1) + _themes.length) % _themes.length];
  setTheme(next);
  showCmd(`THEME → ${next.toUpperCase()}`);
}

// ── Help overlay ──────────────────────────────────────────────────────────────

let _helpVisible = false;
function toggleHelp() {
  _helpVisible = !_helpVisible;
  let overlay = el('pf-help-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id        = 'pf-help-overlay';
    overlay.className = 'pf-help-overlay';
    overlay.innerHTML = `
<div class="pf-help-box">
  <div class="pf-help-title">D.I.M — KEYBOARD SHORTCUTS</div>
  <div class="pf-help-cols">

    <div class="pf-help-col">
      <div class="pf-help-section">TRANSPORT</div>
      <div class="pf-help-grid">
        <div>[SPACE]</div><div>Play / Pause</div>
        <div>[R]</div><div>Rewind</div>
        <div>[S]</div><div>Stop</div>
        <div class="pf-help-combo">[⌘←]</div><div>Rewind <span class="pf-help-mac">⌘</span></div>
        <div class="pf-help-combo">[⌘.]</div><div>Stop <span class="pf-help-mac">⌘</span></div>
        <div class="pf-help-combo">[Ctrl+Space]</div><div>Play/Pause <span class="pf-help-mac">⌘</span></div>
      </div>

      <div class="pf-help-section">TEMPO</div>
      <div class="pf-help-grid">
        <div>[↑] / [↓]</div><div>BPM +1 / −1</div>
        <div>[⇧↑] / [⇧↓]</div><div>BPM +5 / −5</div>
        <div class="pf-help-combo">[⌘↑] / [⌘↓]</div><div>BPM +10 / −10 <span class="pf-help-mac">⌘</span></div>
        <div>[P P P P]</div><div>Tap tempo (4 taps)</div>
      </div>

      <div class="pf-help-section">TIME SIGNATURE</div>
      <div class="pf-help-grid">
        <div>[G]</div><div>Cycle → 4/4 · 3/4 · 6/8 · 5/4 · 7/8</div>
        <div>[⇧G]</div><div>Cycle ←</div>
      </div>
    </div>

    <div class="pf-help-col">
      <div class="pf-help-section">LANE FOCUS</div>
      <div class="pf-help-grid">
        <div>[1–9]</div><div>Focus lane N</div>
        <div>[←] / [→]</div><div>Lane précédente / suivante</div>
        <div>[0]</div><div>Effacer le focus</div>
      </div>

      <div class="pf-help-section">ADVANCE MANUEL</div>
      <div class="pf-help-grid">
        <div>[↵]</div><div>Avancer lane focalisée (ou 1ère en attente)</div>
        <div>[A]</div><div>Avancer TOUTES les lanes en attente</div>
        <div class="pf-help-combo">[⌘↵]</div><div>Avancer TOUTES <span class="pf-help-mac">⌘</span></div>
      </div>

      <div class="pf-help-section">BRANCHES</div>
      <div class="pf-help-grid">
        <div>[V]</div><div>Véto JUMP — lane focalisée</div>
      </div>

      <div class="pf-help-section">VUE</div>
      <div class="pf-help-grid">
        <div>[+] / [−]</div><div>Zoom avant / arrière</div>
        <div class="pf-help-combo">[⌘+] / [⌘−]</div><div>Zoom <span class="pf-help-mac">⌘</span></div>
        <div class="pf-help-combo">[⌘0]</div><div>Zoom 100% <span class="pf-help-mac">⌘</span></div>
        <div>[\\]</div><div>Reset zoom</div>
        <div>[T] / [⇧T]</div><div>Thème suivant / précédent</div>
        <div>[E]</div><div>Éditeur</div>
        <div>[H] / [⌘/]</div><div>Cette aide</div>
      </div>
    </div>

  </div>
  <div class="pf-help-close">
    <span class="pf-help-mac">⌘</span> = combos Mac disponibles en plus des touches simples
    &nbsp;·&nbsp; [H] ou [ESC] pour fermer
  </div>
</div>`;
    overlay.addEventListener('click', () => { _helpVisible = false; overlay.remove(); });
    document.body.appendChild(overlay);
  } else {
    overlay.remove();
  }
}

// ── Keyboard shortcuts ────────────────────────────────────────────────────────

// Init zoom and timesig on load
applyZoom(_zoomIdx);
document.addEventListener('DOMContentLoaded', initTimeSigIdx);

document.addEventListener('keydown', function (e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' ||
      e.target.tagName === 'SELECT') return;

  const cmd  = e.metaKey;   // ⌘ Mac
  const ctrl = e.ctrlKey;
  const shift = e.shiftKey;
  const mod  = cmd || ctrl; // any modifier

  // ── ⌘ / Ctrl combos (Mac HIG) ────────────────────────────────────────────
  if (mod) {
    switch (e.code) {
      // ⌘Space / Ctrl+Space — Play/Pause  (⌘Space intercepté par Spotlight → Ctrl préféré)
      case 'Space':
        e.preventDefault();
        transport('toggle');
        return;

      // ⌘. — Stop  (convention Mac : interrompre une opération)
      case 'Period':
        e.preventDefault();
        transport('stop');
        return;

      // ⌘← — Rewind  (navigation debut, cohérent avec les médias)
      case 'ArrowLeft':
        e.preventDefault();
        transport('rewind');
        return;

      // ⌘↑ / ⌘↓ — BPM ±10 (⇧ déjà utilisé pour ±5)
      case 'ArrowUp':
        e.preventDefault();
        if (_state?.tempo_bpm) setTempo(Math.min(300, (_state.tempo_bpm || 120) + 10));
        return;
      case 'ArrowDown':
        e.preventDefault();
        if (_state?.tempo_bpm) setTempo(Math.max(20, (_state.tempo_bpm || 120) - 10));
        return;

      // ⌘↵ — Advance ALL waiting lanes
      case 'Enter':
      case 'NumpadEnter':
        e.preventDefault();
        advanceAllWaiting();
        return;

      // ⌘= / ⌘+ — Zoom in   |   ⌘- — Zoom out   |   ⌘0 — Zoom reset
      case 'Equal':
      case 'NumpadAdd':
        e.preventDefault();
        zoomIn();
        return;
      case 'Minus':
      case 'NumpadSubtract':
        e.preventDefault();
        zoomOut();
        return;
      case 'Digit0':
      case 'Numpad0':
        e.preventDefault();
        zoomReset();
        return;

      // ⌘/ — Help overlay  (convention Mac : aide contextuelle)
      case 'Slash':
        e.preventDefault();
        toggleHelp();
        return;
    }
    // Laisser les autres combos ⌘ au navigateur (⌘R refresh, ⌘T new tab…)
    return;
  }

  // ── Single-key shortcuts (mode performance) ───────────────────────────────
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

    // ── Tempo ──
    case 'ArrowUp':
      e.preventDefault();
      if (_state?.tempo_bpm) setTempo(Math.min(300, (_state.tempo_bpm || 120) + (shift ? 5 : 1)));
      break;
    case 'ArrowDown':
      e.preventDefault();
      if (_state?.tempo_bpm) setTempo(Math.max(20, (_state.tempo_bpm || 120) - (shift ? 5 : 1)));
      break;
    case 'KeyP':
      tapTempo();
      break;

    // ── Time signature ──
    case 'KeyG':
      cycleTimeSig(shift);
      break;

    // ── Lane focus ──
    case 'ArrowLeft':
      e.preventDefault();
      if (_focusedLane >= 0) focusRelative(-1);
      break;
    case 'ArrowRight':
      e.preventDefault();
      if (_focusedLane >= 0) focusRelative(1);
      break;

    // ── Manual advance ──
    case 'Enter':
    case 'NumpadEnter': {
      e.preventDefault();
      const lanes = getLaneMeta();
      if (_focusedLane >= 0 && lanes[_focusedLane]?.waiting) {
        advanceLane(lanes[_focusedLane].id);
      } else if (_focusedLane >= 0) {
        showCmd('LANE NOT WAITING');
      } else {
        const w = lanes.find(l => l.waiting);
        if (w) advanceLane(w.id);
        else   showCmd('NO LANE WAITING');
      }
      break;
    }
    case 'KeyA':
      advanceAllWaiting();
      break;

    // ── Veto JUMP ──
    case 'KeyV':
      vetoJump();
      break;

    // ── Zoom ──
    case 'Equal':
    case 'NumpadAdd':
      e.preventDefault();
      zoomIn();
      break;
    case 'Minus':
    case 'NumpadSubtract':
      e.preventDefault();
      zoomOut();
      break;
    case 'Backslash':
    case 'NumpadDecimal':
      zoomReset();
      break;

    // ── Theme ──
    case 'KeyT':
      cycleTheme(shift);
      break;

    // ── View ──
    case 'KeyE':
      window.location.href = '/editor';
      break;
    case 'KeyH':
    case 'Escape':
      if (e.code === 'Escape' && !_helpVisible) break;
      toggleHelp();
      break;

    // ── Lane focus 1–9 + 0 ──
    default:
      if (e.code.startsWith('Digit')) {
        const n = parseInt(e.key);
        if (n >= 1 && n <= 9) { e.preventDefault(); focusLane(n); }
        if (n === 0)           { e.preventDefault(); clearFocus(); }
      }
  }
});
