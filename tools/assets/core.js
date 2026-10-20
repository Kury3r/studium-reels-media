/* Shared runtime for every Studium reel format. Loaded before the format's own script.
   Provides: helpers, voice segments (seg), sound cues (SFX), background, tag pill, word-by-word subtitles,
   shared outro (logo, slogans, QR), and finish() that exports window.render / DURATION / SFX / SEGMENTS. */
const EP = window.EP;
const VOICE = EP.voice || {};             // seg id -> seconds of real audio (filled by make_reel.py)
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const prog = (t, a, b) => clamp((t - a) / (b - a));
const lerp = (a, b, k) => a + (b - a) * k;
const eOut = k => 1 - Math.pow(1 - k, 3);
const eIn = k => k * k * k;
const eIO = k => k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
const eBack = k => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); };
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const subOf = s => String(s).replace(/\[[^\]]*\]/g, '').replace(/\s+/g, ' ').trim();
const css = (el, o) => Object.assign((typeof el === 'string' ? $(el) : el).style, o);
// "*word*" -> highlighted word, "\n" -> line break
const rich = s => esc(s).replace(/\*([^*]+)\*/g, '<span class="hl">$1</span>').replace(/\n/g, '<br>');
const plain = s => String(s).replace(/\*/g, '');
const vdur = (id, text) => VOICE[id] !== undefined ? VOICE[id] : 0.35 + subOf(text).length * 0.068;

const SFX = [];   // [t, kind, arg]
const SEGS = [];  // voice lines: {id, at, dur, sub, text}
function seg(id, text, at, sub) {
  if (!text) return 0;
  const d = vdur(id, text);
  SEGS.push({ id, at, dur: d, sub: sub !== undefined ? sub : subOf(text), text: String(text) });
  return d;
}

// ---------- background ----------
(function () {
  const bg = document.createElement('div'); bg.id = 'bg';
  // soft light spots: radial gradients look like the old blurred circles but cost nothing to redraw
  const spot = (id, size, rgb) => `<div class="glow" id="${id}" style="width:${size}px;height:${size}px;margin:-60px 0 0 -60px;` +
    `background:radial-gradient(circle,rgba(${rgb},1) 0%,rgba(${rgb},.85) 30%,rgba(${rgb},.35) 55%,rgba(${rgb},0) 72%)"></div>`;
  bg.innerHTML = spot('g1', 500, '143,240,216') + spot('g2', 460, '169,200,255') + spot('g3', 380, '200,255,240');
  document.body.prepend(bg);
  const tag = document.createElement('div'); tag.id = 'tag'; tag.innerHTML = '<span></span>'; document.body.appendChild(tag);
  const sub = document.createElement('div'); sub.id = 'sub'; document.body.appendChild(sub);
})();
function renderBg(tt) {
  css('g1', { left: `${-120 + 40 * Math.sin(tt * .23)}px`, top: `${60 + 30 * Math.cos(tt * .19)}px` });
  css('g2', { left: `${280 + 40 * Math.cos(tt * .21)}px`, top: `${560 + 40 * Math.sin(tt * .17)}px` });
  css('g3', { left: `${200 + 60 * Math.sin(tt * .13 + 1)}px`, top: `${300 + 50 * Math.cos(tt * .15)}px` });
}
function setTag(text) { const s = document.querySelector('#tag span'); s.textContent = text || ''; $('tag').style.display = text ? '' : 'none'; }
function renderTag(op) { $('tag').style.opacity = op; }

// ---------- subtitles: chunks of a few words, each word appears as it is spoken ----------
function buildChunks(s) {
  const words = s.sub.split(' ').filter(Boolean);
  if (!words.length) return [];
  const chunks = []; let cur = [], len = 0;
  for (const w of words) {
    if (cur.length && (cur.length >= 5 || len + w.length + 1 > 27)) { chunks.push(cur); cur = []; len = 0; }
    cur.push(w); len += w.length + 1;
    if (/[.!?…»]$/.test(w) && len > 10) { chunks.push(cur); cur = []; len = 0; }
  }
  if (cur.length) chunks.push(cur);
  // time is shared by characters (+ a little per word), so long words stay on screen longer
  const weight = w => w.replace(/[«»"“”.,!?…:;—-]/g, '').length + 2;
  const total = chunks.flat().reduce((a, w) => a + weight(w), 0);
  let t = s.at;
  return chunks.map(ws => {
    const start = t;
    const times = ws.map(w => { const a = t; t += s.dur * weight(w) / total; return a; });
    return { start, end: t, words: ws, times };
  });
}
let SUBS = null, subHidden = () => false, lastChunk = null;
function renderSubs(tt) {
  if (!SUBS) SUBS = SEGS.filter(s => s.sub).flatMap(buildChunks);
  let ch = null;
  for (const c of SUBS) if (tt >= c.start - 0.02 && tt < c.end + 0.12) ch = c;
  const box = $('sub');
  if (!ch || subHidden(tt)) { box.style.opacity = 0; return; }
  box.style.opacity = 1;
  if (ch !== lastChunk) {
    box.innerHTML = '<span class="sbox">' + ch.words.map(w => `<span class="w">${esc(w)}</span>`).join(' ') + '</span>';
    lastChunk = ch;
  }
  const pop = eBack(prog(tt, ch.start - 0.02, ch.start + 0.16));
  box.firstChild.style.transform = `scale(${lerp(0.92, 1, pop)})`;
  box.querySelectorAll('.w').forEach((el, i) => {
    const a = ch.times[i], b = i + 1 < ch.times.length ? ch.times[i + 1] : ch.end;
    const k = eOut(prog(tt, a - 0.03, a + 0.12));
    el.style.opacity = tt < a - 0.03 ? 0.3 : lerp(0.3, 1, k);   // upcoming words wait faintly, then light up as spoken
    el.style.transform = `translateY(${(1 - k) * 6}px)`;
    el.classList.toggle('on', tt >= a - 0.03 && tt < b);
  });
}
function hideSubsWhen(fn) { subHidden = fn; }

// ---------- shared outro: logo, slogans, QR to the bot ----------
function buildOutro(slogan, slogan2, opts = {}) {
  const o = document.createElement('div'); o.id = 'outro';
  o.innerHTML = '<div id="logo"><svg width="60" height="80" viewBox="0 0 64 84"><g fill="#1d4a3a"><rect x="2" y="0" width="60" height="8"/><rect x="8" y="12" width="48" height="8" rx="4"/>' +
    '<rect x="12" y="22" width="40" height="40" rx="2"/><rect x="8" y="64" width="48" height="8" rx="4"/><rect x="2" y="76" width="60" height="8"/></g>' +
    '<g fill="#eaf7f3"><rect x="19" y="26" width="4" height="32" rx="2"/><rect x="30" y="26" width="4" height="32" rx="2"/><rect x="41" y="26" width="4" height="32" rx="2"/></g></svg></div>' +
    '<div id="word">STUDIUM</div><div class="sl" id="sl1" style="top:318px"></div><div class="sl" id="sl2" style="top:362px;color:#0a8f86;font-size:26px"></div>' +
    '<div id="qr"></div>';
  document.body.appendChild(o);
  $('sl1').textContent = slogan || 'Studium';
  $('sl2').textContent = slogan2 || 'Перші 2 тижні безкоштовно';
  if (opts.small1) $('sl1').style.fontSize = opts.small1 + 'px';
  const src = $('qrsrc'); $('qr').innerHTML = (src ? src.innerHTML : '') + '<b>@CRM_StudiumBot</b>';
  o.style.opacity = 0;
}
function renderOutro(tt, OUT_IN) {
  const oi = prog(tt, OUT_IN, OUT_IN + 0.7);
  $('outro').style.opacity = clamp(oi * 2.5);
  css('logo', { transform: `scale(${oi > 0 ? lerp(.5, 1, eBack(prog(tt, OUT_IN, OUT_IN + 0.55))) : .5})` });
  [['word', 0.25], ['sl1', 0.45], ['sl2', 0.75], ['qr', 1.0]].forEach(([id, d]) => {
    const k = eOut(prog(tt, OUT_IN + d, OUT_IN + d + 0.45));
    css(id, { opacity: k, transform: `translateY(${(1 - k) * 22}px)` });
  });
  return oi;
}
// Standard outro timing for non-chat formats: returns {OUT_IN, END}
function outroTimeline(at) {
  const O = EP.outro || {};
  SFX.push([at, 'whoosh'], [at + 0.5, EP.kind === 'sell' ? 'success' : 'ding']);
  const d = seg('outro', O.say || 'Студіум. Підключайте в боті Сі-Ар-Ем Студіум.', at + 0.45,
    O.sub !== undefined ? O.sub : (O.say ? undefined : 'Studium. Підключайте в боті @CRM_StudiumBot'));
  return { OUT_IN: at, END: at + 0.45 + Math.max(d, 2.4) + 0.7 };
}

// glass hand cursor svg
const HAND_SVG = '<svg viewBox="0 0 60 78" width="58"><path d="M18 4c4 0 6.5 3 6.5 7v22l3-2.2c3.2-2.2 7.6-1 9.2 2.4l.4.9 2-1.1c3.4-1.8 7.5-.2 8.8 3.4l.3.8 1.5-.6c3.6-1.3 7.4 1.2 7.6 5l.3 13c.3 11-7.5 20.4-18.4 21.8l-6 .8C24.8 79.6 17.6 76 14 69.6L3.6 51.4c-1.8-3.2-.8-7.2 2.3-9.1 3-1.9 7-1.2 9.2 1.6l-2.6-3.4V11c0-4 2.5-7 5.5-7z" ' +
  'fill="rgba(255,255,255,.92)" stroke="#14b89f" stroke-width="2.4" stroke-linejoin="round"/></svg>';

// ---------- finish: export the frame function ----------
function finish(END, renderFn) {
  const render = tt => { renderBg(tt); renderFn(tt); renderSubs(tt); };
  window.render = render; window.DURATION = END; window.SFX = SFX;
  window.SEGMENTS = SEGS.map(s => ({ id: s.id, at: +s.at.toFixed(3), dur: +s.dur.toFixed(3), sub: s.sub, text: s.text }));
  render(0);
  if (location.search.includes('play')) { const t0 = performance.now(); const loop = () => { render(((performance.now() - t0) / 1000) % END); requestAnimationFrame(loop); }; loop(); }
}
