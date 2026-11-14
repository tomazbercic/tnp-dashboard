// Records 3D MAP 013/100: the TNP dashboard in use, 1080 x 1350, 30 fps, frame by frame in headless Chrome.
// Time is virtual: the page's clock and requestAnimationFrame advance exactly 1/30 s per captured frame,
// and the mouse is real input (hover, clicks, drags, wheel), drawn as a cursor on the stage.
//   node rec.mjs                      -> MP4 + PNG of the last frame (env FFMPEG = path to ffmpeg, OUT = mp4 path); no web server needed
//   STILLS="6,13.5,40" node rec.mjs   -> PNG stills only, for checking the layout
import { launch } from './cdp.mjs';
import { spawn } from 'node:child_process';
import { writeFileSync, mkdirSync, rmSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const FPS = 30, DUR = +(process.env.DUR || 50);
const STILLS = process.env.STILLS ? process.env.STILLS.split(',').map(Number) : null;
const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = process.env.OUT || join(HERE, 'out', '3DMAP_013_tnp-dashboard_v1_2026-11-14.mp4');
const ROOT = join(HERE, '..');   // project folder: served to the page straight from disk, no web server needed
const URL0 = 'http://tnp.local/video/stage.html';
const MIME = {'.html':'text/html; charset=utf-8','.json':'application/json','.js':'text/javascript','.mjs':'text/javascript','.jpg':'image/jpeg','.png':'image/png','.css':'text/css'};
const IF = `document.getElementById('frame')`;

// ---------- script: captions, cursor moves and actions (seconds) ----------
const CAPS = [
  [0.3, 4.9, 'A week in the park, replayed hour by hour', 'Teden v parku, predvajan ura za uro'],
  [5.2, 10.2, 'Point at a counter to see each day', 'Ob števcu se pokaže obisk po dnevih'],
  [10.5, 16.3, 'Windows open, fold away and move aside', 'Okna se odprejo, pomanjšajo in umaknejo'],
  [16.6, 22.6, 'The legend switches layers on and off', 'Legenda vklaplja in izklaplja sloje'],
  [22.9, 28.6, 'Zoom in: cable cars, gauges and wind at Bohinj', 'Bližje: žičnice, vodomer in veter v Bohinju'],
  [28.9, 33.6, 'Drag the timeline to any hour of the week', 'Na časovnici izbereš katerokoli uro'],
  [33.9, 38.4, 'Pick any period up to 31 days', 'Izbereš lahko obdobje do 31 dni'],
  [38.8, 43.5, 'The week in numbers', 'Teden v številkah'],
];
const STATS_T = 38.6, SUM_T = 43.8;   // the week in numbers, then the summary frame
const q = s => JSON.stringify(s);
const elAt = expr => async ev => ev(`(() => { const F = ${IF}, r0 = F.getBoundingClientRect(), D = F.contentDocument, e = (${expr}); if (!e) return null;
  const r = e.getBoundingClientRect(); return [r0.left + r.left + r.width/2, r0.top + r.top + r.height/2]; })()`);
const beacon = (name, frac) => async ev => ev(`(() => { const F = ${IF}, r0 = F.getBoundingClientRect(), T = F.contentWindow.__tnp;
  const b = T.beacons.find(b => b.c.name === ${q(name)}); const v = b.g.position.clone(); v.y += b.beam.scale.y*${frac}; v.project(T.camera);
  return [r0.left + (v.x+1)/2*F.clientWidth, r0.top + (1-v.y)/2*F.clientHeight]; })()`);
const tlAt = h => async ev => ev(`(() => { const F = ${IF}, r0 = F.getBoundingClientRect(), r = F.contentDocument.getElementById('tlc').getBoundingClientRect();
  return [r0.left + r.left + r.width*${h}/168, r0.top + r.top + r.height*.5]; })()`);
const off = (fn, dx, dy) => async ev => { const p = await fn(ev); return [p[0]+dx, p[1]+dy]; };
const rowByText = txt => elAt(`[...D.querySelectorAll('#legend .lg>label')].find(l => l.querySelector('span') && l.querySelector('span').textContent.startsWith(${q(txt)}))`);
const busiestCard = `D.getElementById('race').closest('.card')`;
const legendCard = `D.getElementById('legend')`;

const MOVES = [   // cursor glides (cubic ease) from where it is to the target, resolved when the move starts
  {t0: 4.6, t1: 6.2, to: beacon('Dolina Tamar', .3)},
  {t0: 10.3, t1: 11.0, to: elAt(`${busiestCard}.querySelector('.mn')`)},
  {t0: 11.5, t1: 12.1, to: off(elAt(`${busiestCard}.querySelector('h2 .ht')`), -40, 0)},
  {t0: 12.45, t1: 13.7, to: async ev => [560, 430]},
  {t0: 14.9, t1: 15.6, to: elAt(`${busiestCard}.querySelector('.mn')`)},
  {t0: 16.5, t1: 17.3, to: elAt(`${legendCard}.querySelector('.mn')`)},
  {t0: 17.8, t1: 18.4, to: rowByText('Cars')},
  {t0: 19.0, t1: 19.6, to: rowByText('Labels')},
  {t0: 21.0, t1: 21.6, to: elAt(`${legendCard}.querySelector('.mn')`)},
  {t0: 22.3, t1: 23.3, to: off(elAt(`F.contentWindow.__tnp.lakeLabel.element`), 6, 6)},
  {t0: 26.4, t1: 27.6, to: async ev => null, dragBy: [-160, 0]},
  {t0: 28.6, t1: 29.3, to: tlAt(9)},
  {t0: 29.7, t1: 31.4, to: tlAt(14)},
  {t0: 33.6, t1: 34.5, to: elAt(`D.getElementById('rangeBtn')`)},
  {t0: 35.3, t1: 36.0, to: elAt(`D.querySelector('#rangePop [data-n="30"]')`)},
  {t0: 37.0, t1: 37.8, to: async ev => [470, 330]},
];
const CLICKS = [
  {t: 11.15, k: 'click'}, {t: 12.35, k: 'down'}, {t: 13.8, k: 'up'}, {t: 14.5, k: 'dbl'}, {t: 15.8, k: 'click'},
  {t: 17.45, k: 'click'}, {t: 18.55, k: 'click'}, {t: 19.75, k: 'click'}, {t: 20.75, k: 'click'}, {t: 21.75, k: 'click'},
  {t: 26.3, k: 'down'}, {t: 27.7, k: 'up'},
  {t: 29.45, k: 'down'}, {t: 31.5, k: 'up'},
  {t: 34.65, k: 'click'}, {t: 37.95, k: 'click'},
];
const WHEELS = [{t0: 23.5, t1: 26.0, n: 21, dy: -120}, {t0: 27.9, t1: 28.5, n: 9, dy: 120}];
const JS = [   // page state that a viewer would not see being set
  {t: 0, js: `T.seek(29.5); D.getElementById('speed').click(); D.getElementById('speed').click(); T.setPlay(true); T.controls.autoRotate = true;
    T.camera.position.set(-6, 25, 36); T.controls.target.set(0, .3, 3);`},
  {t: 4.7, js: `T.setPlay(false); T.controls.autoRotate = false;`},   // Sunday afternoon, the busiest day; the orbit stops while the pointer works
  {t: STATS_T - .2, js: `T.seek(37); D.body.classList.add('vclean');`},  // clean map for the numbers and the summary
];
const CAM = [{t0: STATS_T - .2, t1: STATS_T + 2.2, pos: [0, 46, 71.5], tgt: [0, 0, 16.5]}];
const CUR_A = [[4.3, 4.7, 0, 1], [STATS_T - .4, STATS_T, 1, 0]];

// ---------- run ----------
const ease = u => u < .5 ? 4*u*u*u : 1 - Math.pow(-2*u + 2, 3)/2;
const profile = join(tmpdir(), 'tnp-rec-profile'); rmSync(profile, {recursive: true, force: true});
const c = await launch({ profile, width: 900, height: 1125 });
const ev = c.evaluate;
const VT = `(() => { let vt = 0; const q = [], seen = new WeakMap();
  performance.now = () => vt;
  window.requestAnimationFrame = cb => { q.push(cb); return q.length; }; window.cancelAnimationFrame = () => {};
  window.__vt = { advance(ms){ vt += ms; for (const cb of q.splice(0)){ try { cb(vt); } catch(e){ console.error(String(e && e.stack || e)); } } },
    anims(ms){ for (const a of document.getAnimations()){ const v = (seen.get(a) ?? 0) + ms; seen.set(a, v); try { a.pause(); a.currentTime = v; } catch(e){} } } }; })();`;
const errors = [];
c.on(m => { if (m.method === 'Runtime.exceptionThrown') errors.push(JSON.stringify(m.params.exceptionDetails).slice(0, 500));
  if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') errors.push(m.params.args.map(a => a.value ?? a.description).join(' ').slice(0, 500)); });
let ff;
try {
  await c.send('Fetch.enable', { patterns: [{ urlPattern: 'http://tnp.local/*', requestStage: 'Request' }] });
  c.on(async m => { if (m.method !== 'Fetch.requestPaused') return;
    const f = join(ROOT, decodeURIComponent(new URL(m.params.request.url).pathname));
    let body = null; try { body = readFileSync(f); } catch {}
    await c.send('Fetch.fulfillRequest', body ? { requestId: m.params.requestId, responseCode: 200, responseHeaders: [{ name: 'Content-Type', value: MIME[extname(f)] || 'application/octet-stream' }], body: body.toString('base64') }
      : { requestId: m.params.requestId, responseCode: 404, responseHeaders: [], body: '' }).catch(() => {}); });
  await c.send('Page.addScriptToEvaluateOnNewDocument', { source: VT });
  await c.send('Emulation.setDeviceMetricsOverride', { width: 900, height: 1125, deviceScaleFactor: 1.2, mobile: false });
  await c.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'no-preference' }] });
  await c.send('Page.navigate', { url: URL0 });
  for (let i = 0; i < 240; i++) { if (await ev(`!!(${IF} && ${IF}.contentWindow && ${IF}.contentWindow.__tnp)`).catch(() => false)) break; await c.sleep(250); }
  await ev(`document.fonts.ready.then(() => true)`);
  await ev(`(() => { const D = ${IF}.contentDocument, st = D.createElement('style');
    st.textContent = '#title,#beat,#sunarc,#suns,#srcwrap{display:none!important}#left{top:14px!important}#clock{top:12px!important}' + '.vclean #left,.vclean #right,.vclean #tl,.vclean #tools,.vclean #legwrap,.vclean #clock,.vclean #tip{opacity:0!important;transition:opacity .45s}'; D.head.appendChild(st); return true; })()`);
  const step = ms => ev(`(() => { const w = ${IF}.contentWindow; w.__vt.advance(${ms}); w.__vt.anims(${ms}); window.__vt.anims(${ms}); return true; })()`);
  for (let i = 0; i < 60; i++) await step(1000/FPS);    // settle layout, labels and damping before the first frame
  await ev(`(() => { ${IF}.contentWindow.dispatchEvent(new Event('resize')); return true; })()`);
  for (let i = 0; i < 15; i++) await step(1000/FPS);

  if (!STILLS) {
    mkdirSync(dirname(OUT), { recursive: true });
    ff = spawn(process.env.FFMPEG, ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
      '-vf', 'sidedata=mode=delete:type=ICC_PROFILE,scale=in_range=pc:out_range=tv:in_color_matrix=bt601:out_color_matrix=bt709,format=yuv420p',
      '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
      '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-r', String(FPS),
      '-bsf:v', 'filter_units=remove_types=6', '-map_metadata', '-1', '-fflags', '+bitexact', '-flags:v', '+bitexact',
      '-metadata', 'title=13/100 One week in Triglav National Park', '-metadata', 'artist=Tomaž Berčič', '-metadata', 'author=Tomaž Berčič',
      '-metadata', 'date=2026-11-14', '-metadata:s:v:0', 'handler_name=', '-metadata:s:v:0', 'encoder=',
      '-movflags', '+faststart+use_metadata_tags', OUT], { stdio: ['pipe', 'inherit', 'inherit'] });
  }
  let cur = [450, 520], down = false, sent = WHEELS.map(() => 0), lastRip = -9, ripAt = [0, 0];
  const camStart = new Map(), N = Math.round(DUR*FPS), t00 = Date.now();
  const mouse = (type, extra = {}) => c.send('Input.dispatchMouseEvent', { type, x: cur[0], y: cur[1], button: down || type !== 'mouseMoved' ? 'left' : 'none', buttons: down ? 1 : 0, ...extra });
  for (let f = 0; f < N; f++) {
    const t = f/FPS, tp = (f-1)/FPS, inStep = x => x > tp && x <= t;
    for (const j of JS) if (inStep(j.t) || (f === 0 && j.t === 0)) await ev(`(() => { const T = ${IF}.contentWindow.__tnp, D = ${IF}.contentDocument; ${j.js} return true; })()`);
    let moved = false;
    for (const m of MOVES) {
      if (t < m.t0 || t > m.t1 + 1/FPS) continue;
      if (!m.started) { m.started = true; m.from = cur.slice(); const p = await m.to(ev);
        m.dest = m.dragBy ? [cur[0] + m.dragBy[0], cur[1] + m.dragBy[1]] : (p || cur.slice()); if (process.env.DEBUG) console.log('move', m.t0, JSON.stringify(p), '->', m.dest.map(Math.round)); }
      const u = ease(Math.min(1, (t - m.t0)/(m.t1 - m.t0))), nx = m.from[0] + (m.dest[0]-m.from[0])*u, ny = m.from[1] + (m.dest[1]-m.from[1])*u;
      if (Math.abs(nx-cur[0]) + Math.abs(ny-cur[1]) > .05) { cur = [nx, ny]; moved = true; }
    }
    if (moved || f === 0) await mouse('mouseMoved');
    for (const k of CLICKS) if (inStep(k.t)) {
      if (k.k === 'down') { down = true; await mouse('mousePressed', { clickCount: 1 }); }
      if (k.k === 'up') { await c.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: cur[0], y: cur[1], button: 'left', buttons: 0, clickCount: 1 }); down = false; }
      if (k.k === 'click' || k.k === 'dbl') { for (const n of k.k === 'dbl' ? [1, 2] : [1]) { down = true; await mouse('mousePressed', { clickCount: n }); down = false;
          await c.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: cur[0], y: cur[1], button: 'left', buttons: 0, clickCount: n }); } }
      if (k.k !== 'up') { lastRip = t; ripAt = cur.slice(); }
    }
    WHEELS.forEach((w, i) => { if (t < w.t0 || t > w.t1 + 1/FPS) return; const want = Math.min(w.n, Math.round(w.n*(t - w.t0)/(w.t1 - w.t0)));
      for (; sent[i] < want; sent[i]++) c.send('Input.dispatchMouseEvent', { type: 'mouseWheel', x: cur[0], y: cur[1], deltaX: 0, deltaY: w.dy }); });
    for (const cm of CAM) if (t >= cm.t0 && t <= cm.t1 + 1/FPS) {
      if (!camStart.has(cm)) camStart.set(cm, await ev(`(() => { const T = ${IF}.contentWindow.__tnp; return [T.camera.position.toArray(), T.controls.target.toArray()]; })()`));
      const [p0, g0] = camStart.get(cm), u = ease(Math.min(1, (t - cm.t0)/(cm.t1 - cm.t0))), L = (a, b) => a.map((v, i) => v + (b[i]-v)*u);
      await ev(`(() => { const T = ${IF}.contentWindow.__tnp; T.controls.autoRotate = false; T.camera.position.fromArray(${q(L(p0, cm.pos))}); T.controls.target.fromArray(${q(L(g0, cm.tgt))}); return true; })()`);
    }
    await step(1000/FPS);
    const capNow = CAPS.find(k => t >= k[0] - .01 && t <= k[1]);
    const capA = capNow ? Math.min(1, (t - capNow[0])/.35, (capNow[1] - t)/.35) : 0;
    const curA = CUR_A.reduce((a, [a0, a1, v0, v1]) => t >= a0 ? (t >= a1 ? v1 : v0 + (v1 - v0)*ease((t - a0)/(a1 - a0))) : a, 0);
    const ru = (t - lastRip)/.45;
    await ev(`setStage(${q({ cap: capNow ? [capNow[2], capNow[3]] : null, capA: Math.max(0, capA), sum: ease(Math.max(0, Math.min(1, (t - SUM_T)/.6))),
      cur: { x: cur[0], y: cur[1], a: curA, down }, statsT: t >= STATS_T + .3 && t < SUM_T + .6 ? t - STATS_T - .3 : null, statsOut: Math.max(0, Math.min(1, (SUM_T + .3 - t)/.5)), rip: ru < 1 ? { x: ripAt[0], y: ripAt[1], a: (1 - ru)*.8*curA, s: .3 + ru } : { a: 0 } })}), true`);
    if (STILLS) {
      if (STILLS.some(s => Math.abs(s - t) < .5/FPS)) { const { data } = await c.send('Page.captureScreenshot', { format: 'png' });
        mkdirSync(join(HERE, 'out'), { recursive: true }); writeFileSync(join(HERE, 'out', `still_${t.toFixed(1)}.png`), Buffer.from(data, 'base64')); console.log('still', t.toFixed(1)); }
      if (t > Math.max(...STILLS)) break;
      continue;
    }
    const { data } = await c.send('Page.captureScreenshot', { format: 'jpeg', quality: 93, optimizeForSpeed: true });
    if (!ff.stdin.write(Buffer.from(data, 'base64'))) await new Promise(r => ff.stdin.once('drain', r));
    if (f === N - 1) { const png = await c.send('Page.captureScreenshot', { format: 'png' }); writeFileSync(OUT.replace(/\.mp4$/, '.png'), Buffer.from(png.data, 'base64')); }
    if (f % 150 === 0) console.log(`frame ${f}/${N}, ${((Date.now() - t00)/1000).toFixed(0)} s`);
  }
  if (ff) { ff.stdin.end(); await new Promise(r => ff.on('close', r)); }
  console.log(errors.length ? 'page errors:\n' + errors.join('\n') : 'no page errors');
} finally { await c.close(); }
