"use strict";
/*
 * D.I.M — esp32_preview.js
 * Emulates what an ESP32 with a HD44780 LCD or SSD1306 OLED would display.
 * Subscribes to the same SocketIO feed as the performance view.
 */

// ── State ─────────────────────────────────────────────────────────────────────

let _state  = null;
let _mode   = localStorage.getItem('esp32-mode')    || 'lcd20x4';
let _palette = localStorage.getItem('esp32-palette') || 'amber';

// ── Mode / palette ────────────────────────────────────────────────────────────

function setMode(mode) {
  _mode = mode;
  localStorage.setItem('esp32-mode', mode);
  document.querySelectorAll('.esp32-device').forEach(d => d.classList.add('hidden'));
  const dev = document.getElementById('device-' + mode);
  if (dev) dev.classList.remove('hidden');
  document.querySelectorAll('.esp32-mode-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === mode);
  });
  if (_state) render(_state);
}

function setPalette(pal) {
  _palette = pal;
  localStorage.setItem('esp32-palette', pal);
  document.documentElement.dataset.palette = pal;
  document.querySelectorAll('.esp32-pal-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.pal === pal);
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Pad/truncate a string to exactly n chars */
function pad(s, n) {
  s = String(s || '');
  if (s.length > n) return s.substring(0, n);
  return s + ' '.repeat(n - s.length);
}

function esc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** Format bar number with leading zeros to 3 digits */
function bar3(n) { return String(n || 0).padStart(3, '0'); }

/** Compact BPM — 5 chars: "118.0" */
function bpmStr(b) { return (b || 0).toFixed(1); }

// ── LCD 20×4 renderer ─────────────────────────────────────────────────────────
/*
  Row 0: "BPM:118.0  ▶ B:099"   (20 chars)
  Row 1: "TS:4/4   [PLAYING]  "
  Row 2: "⊛ Hold intro    ↺ ⊙"  conductor current cue
  Row 3: "1 Groove A          " first non-conductor lane
*/

function renderLcd(state) {
  const bpm    = bpmStr(state.tempo_bpm);
  const bar    = bar3(state.bar);
  const beat   = state.beat_in_bar || 1;
  const ts     = state.time_signature || '4/4';
  const play   = state.playing;
  const lanes  = Object.values(state.lanes || {});
  const cond   = lanes.find(l => l.is_conductor);
  const others = lanes.filter(l => !l.is_conductor);

  // Status string (8 chars)
  const anyWait = lanes.some(l => l.waiting_manual);
  const status8 = anyWait
    ? ' WAIT.. '
    : (play ? ' PLAY.. ' : ' STOP.. ');

  // Row 0: BPM + transport + bar  (20 chars)
  const row0 = pad(`BPM:${bpm}  ${play ? '▶' : '■'} B:${bar}`, 20);

  // Row 1: TS + beat + status (20 chars)
  const row1 = pad(`TS:${ts} ’${beat} ${status8}`, 20);

  // Row 2: conductor cue (20 chars)
  let row2 = '';
  if (cond) {
    const cue   = cond.cue?.label || (cond.ended ? 'END' : '---');
    const badge = cond.cue?.badge || '';
    const waiting = cond.waiting_manual ? '⊙ ' : '⊛ ';
    row2 = pad(waiting + pad(cue, 14) + pad(badge, 4), 20);
  } else {
    row2 = pad('', 20);
  }

  // Row 3: first other lane current cue (20 chars)
  let row3 = '';
  if (others.length > 0) {
    const l    = others[0];
    const n    = l.name.substring(0, 6).toUpperCase();
    const cue  = l.cue?.label || (l.ended ? 'END' : '---');
    const wait = l.waiting_manual ? '⊙' : ' ';
    row3 = pad(`${wait}${n}: ${cue}`, 20);
  } else {
    row3 = pad('', 20);
  }

  // Write rows
  const rows = [row0, row1, row2, row3];
  rows.forEach((txt, i) => {
    const el = document.getElementById('lcd-row-' + i);
    if (el) el.textContent = txt;
  });
}

// ── OLED 128×64 renderer ──────────────────────────────────────────────────────
/*
  Header: "D.I.M ▶ 118.0 BPM"
  Sub:    "BAR:099  BEAT:3  4/4"
  ─────────────────────────────
  ⊛ CONDUCTOR: Hold intro  ↺⊙
  1 DRUMS:     Groove A
  2 SYNTH:     LFO slow
  3 FX:        Granular atmo
*/

function renderOled128(state) {
  const bpm   = bpmStr(state.tempo_bpm);
  const bar   = bar3(state.bar);
  const beat  = state.beat_in_bar || 1;
  const ts    = state.time_signature || '4/4';
  const play  = state.playing;
  const lanes = Object.values(state.lanes || {});
  const cond  = lanes.find(l => l.is_conductor);
  const others = lanes.filter(l => !l.is_conductor);

  const playIcon = play ? '▶' : '■';
  setText128('oled-h-128',   `D.I.M ${playIcon} ${bpm} BPM`);
  setText128('oled-pos-128', `BAR:${bar}  BT:${beat}  ${ts}`);

  const allLanes = [cond, ...others].filter(Boolean);
  const cueEls   = ['oled-c0-128','oled-c1-128','oled-c2-128','oled-c3-128'];

  cueEls.forEach((id, i) => {
    const el = document.getElementById(id);
    if (!el) return;
    const l = allLanes[i];
    if (!l) { el.textContent = ''; el.className = 'oled-row oled-cue'; return; }

    const prefix = l.is_conductor ? '⊛' : String(i);
    const name   = l.name.substring(0, 8).toUpperCase().padEnd(8);
    const cue    = (l.cue?.label || (l.ended ? 'END' : '---')).substring(0, 14).padEnd(14);
    const badge  = (l.cue?.badge || '').substring(0, 4);
    el.textContent = `${prefix} ${name} ${cue} ${badge}`;

    el.className = 'oled-row oled-cue' +
      (l.waiting_manual ? ' waiting' : '') +
      (i === 0 ? ' active' : '') +
      (l.ended ? ' dim' : '');
  });
}

function setText128(id, txt) {
  const el = document.getElementById(id);
  if (el) el.textContent = txt;
}

// ── OLED 128×32 renderer ──────────────────────────────────────────────────────
/*
  Header: "118.0BPM ▶ BAR:099 4/4"
  Cue 0:  Conductor
  Cue 1:  First other lane
*/

function renderOled32(state) {
  const bpm   = bpmStr(state.tempo_bpm);
  const bar   = bar3(state.bar);
  const play  = state.playing;
  const ts    = state.time_signature || '4/4';
  const lanes = Object.values(state.lanes || {});
  const cond  = lanes.find(l => l.is_conductor);
  const others = lanes.filter(l => !l.is_conductor);

  const s32 = id => document.getElementById(id);
  if (s32('oled-h-32'))
    s32('oled-h-32').textContent = `${bpm}BPM ${play?'▶':'■'} B:${bar} ${ts}`;

  const rows = [cond, others[0]].filter(Boolean);
  ['oled-c0-32','oled-c1-32'].forEach((id, i) => {
    const el = s32(id);
    if (!el) return;
    const l = rows[i];
    if (!l) { el.textContent = ''; el.className = 'oled-row oled-cue oled32-cue'; return; }
    const prefix = l.is_conductor ? '⊛' : (l.name[0] || String(i+1));
    const cue    = (l.cue?.label || (l.ended ? 'END' : '---')).substring(0, 18);
    const wait   = l.waiting_manual ? ' ⊙' : '';
    el.textContent = `${prefix} ${cue}${wait}`;
    el.className = 'oled-row oled-cue oled32-cue' + (l.waiting_manual ? ' waiting' : '');
  });
}

// ── Main render dispatcher ────────────────────────────────────────────────────

function render(state) {
  if (!state || !state.loaded) return;
  try {
    if (_mode === 'lcd20x4')  renderLcd(state);
    if (_mode === 'oled128')  renderOled128(state);
    if (_mode === 'oled32')   renderOled32(state);
  } catch(e) { /* defensive */ }
  updateSidebar(state);
}

function updateSidebar(state) {
  const el = id => document.getElementById(id);
  const lanes = Object.values(state.lanes || {});

  const setText = (id, t) => { const e = el(id); if (e) e.textContent = t; };
  setText('esp-bpm',    (state.tempo_bpm || 0).toFixed(1) + ' BPM');
  setText('esp-bar',    state.bar || '—');
  setText('esp-beat',   state.beat_in_bar || '—');

  const anyWait = lanes.some(l => l.waiting_manual);
  const status  = anyWait ? '⊙ WAITING' : (state.playing ? '▶ PLAYING' : '■ STOPPED');
  setText('esp-status', status);

  const lanesDiv = el('esp-lanes');
  if (lanesDiv) {
    lanesDiv.innerHTML = lanes.map(l => {
      const cue   = l.cue?.label || (l.ended ? 'END' : '—');
      const badge = l.cue?.badge || '';
      const wait  = l.waiting_manual ? ' ⊙' : '';
      return `<div class="esp32-data-row"><span>${l.name.substring(0,10)}</span>` +
             `<span>${cue.substring(0,16)}${badge ? ' '+badge : ''}${wait}</span></div>`;
    }).join('');
  }
}

// ── SocketIO ──────────────────────────────────────────────────────────────────

socket.on('connect', () => {
  const el = document.getElementById('esp-sock');
  if (el) { el.textContent = '● LIVE'; el.style.color = '#32cd32'; }
});
socket.on('disconnect', () => {
  const el = document.getElementById('esp-sock');
  if (el) { el.textContent = '○ OFFLINE'; el.style.color = '#555'; }
});
socket.on('state_update', function(state) {
  _state = state;
  render(state);
});

// ── Init ──────────────────────────────────────────────────────────────────────

setMode(_mode);
setPalette(_palette);
