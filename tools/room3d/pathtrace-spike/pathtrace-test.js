// Stage 0 spike: path-traced render of the viewer's own scene (three-gpu-pathtracer, WebGPU, OIDN denoiser).
// The viewer (three r187 here) keeps its WebGL canvas; the render goes to a second canvas on top. While the render is on,
// the viewer's loop is stopped (the GPU is the tracer's), its fake lights are off (hemisphere, sky panel in the window,
// floor-patch bounce) and a sky environment outside lights the room through the glass instead.
import * as THREE from 'three/webgpu';
import { WebGPUPathTracer, OIDNDenoiser } from 'three-gpu-pathtracer/webgpu';
import { initUNetFromURL } from 'oidn-webgpu';

const WEIGHTS = 'https://cdn.jsdelivr.net/gh/pissang/oidn-webgpu@main/weights/rt_hdr_alb_nrm.tza';
const until = async f => { while (!f()) await new Promise(r => setTimeout(r, 100)); return f(); };
const V = await until(() => window.__pt);

// ---------- UI ----------
const css = document.createElement('style');
css.textContent = `
  #ptc { position: fixed; inset: 0; width: 100vw; height: 100vh; display: none; pointer-events: none; z-index: 2; }
  #ptbar { position: fixed; left: 50%; transform: translateX(-50%); bottom: 14px; z-index: 20; display: flex; gap: 6px; align-items: center;
    padding: 6px 10px; border-radius: 10px; background: rgba(28,28,30,.88); color: #eee; font: 12px system-ui, sans-serif; }
  #ptbar button, #ptbar select { font: inherit; padding: 4px 9px; border-radius: 6px; border: 1px solid #555; background: #333; color: #eee; cursor: pointer; }
  #ptbar button.on { background: #3d6e8c; border-color: #3d6e8c; }
  #ptstat { min-width: 270px; font-variant-numeric: tabular-nums; opacity: .9; }`;
document.head.append(css);
const canvas = Object.assign(document.createElement('canvas'), { id: 'ptc' });
document.body.append(canvas);
const bar = document.createElement('div'); bar.id = 'ptbar';
bar.innerHTML = `<button id="ptgo">Рендер</button>
  <select id="ptspp" title="Сколько сэмплов на пиксель накопить"><option value="64">64</option><option value="256" selected>256</option><option value="1024">1024</option><option value="0">без конца</option></select>
  <select id="ptbounce" title="Отражений луча"><option value="4">4 отр.</option><option value="8" selected>8 отр.</option><option value="15">15 отр.</option></select>
  <select id="ptexp" title="Экспозиция: множитель к экспозиции вьюера"><option value="0.25">эксп. ×0,25</option><option value="0.4" selected>эксп. ×0,4</option><option value="0.6">эксп. ×0,6</option><option value="1">эксп. ×1</option></select>
  <button id="ptdn" class="on" title="Денойзер Intel OIDN после последнего сэмпла">Денойзер</button>
  <button id="ptsave" title="Сохранить кадр PNG">PNG</button>
  <span id="ptstat">WebGPU: ${navigator.gpu ? 'есть' : 'нет'}</span>`;
document.body.append(bar);
const $ = id => document.getElementById(id);

// ---------- the tracer ----------
const renderer = new THREE.WebGPURenderer({ canvas, antialias: false, trackTimestamp: true });   // timestamps: adaptive frame budget
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.toneMapping = THREE.NeutralToneMapping;
await renderer.init();
const pt = new WebGPUPathTracer(renderer);
Object.assign(pt, { filterGlossyFactor: .5, clampIndirect: 0, maxBounces: 8, maxSamples: 256 });
let denoise = true, denoiser = null;
function setDenoise(on) {
  denoise = on; $('ptdn').classList.toggle('on', on);
  if (on && !denoiser) denoiser = new OIDNDenoiser({ initUNetFromURL, auxWeightsUrl: WEIGHTS });
  pt.setDenoiser(on ? denoiser : null);
}
setDenoise(true);
window.__tracer = pt;

// ---------- sky outside: an equirect HDR environment in the viewer's units (cd/m2 x LUX), camera white balance included ----------
// clear: brighter towards the horizon (that is what a window mostly sees), sunlit ground below;
// overcast: the CIE overcast sky (zenith 3x the horizon), ground lit by it; evening: a faint dark-blue glow.
function skyTexture(mode) {
  const wb = V.MODES[mode].wb, sky = V.envOf('sky'), sunO = V.envOf('sun');
  const W = 256, Hh = 128, data = new Float32Array(W * Hh * 4);
  const skyCol = V.lightColor(mode === 'cloud' ? sky?.kelvin_overcast ?? 6500 : mode === 'sun' ? sky?.kelvin ?? 8000 : 12000, wb);
  const groundCol = V.lightColor(mode === 'sun' ? sunO?.kelvin ?? 5300 : 6500, wb).multiply(new THREE.Color(.85, .8, .7));
  const L = mode === 'sun' ? sky?.luminance ?? 5000 : mode === 'cloud' ? sky?.overcast ?? 2500 : .4;
  const sunE = mode === 'sun' && sunO ? (sunO.illuminance ?? 80000) * Math.sin(THREE.MathUtils.degToRad(sunO.altitude ?? 32)) : 0;
  const Lz = 1.6 * L;                                                        // overcast: zenith luminance for a window average of L
  for (let y = 0; y < Hh; y++) {
    const el = ((y + .5) / Hh - .5) * Math.PI, s = Math.sin(el);             // DataTexture row 0 = v 0 = straight down
    let lum, col;
    if (el >= 0) {
      lum = mode === 'cloud' ? Lz * (1 + 2 * s) / 3 : mode === 'sun' ? L * (1.25 - .65 * s) : L;
      col = skyCol;
    } else {
      lum = mode === 'sun' ? .2 * sunE / Math.PI + .25 * L : mode === 'cloud' ? .2 * (7 / 9) * Lz : .15 * L;
      col = groundCol;
    }
    for (let x = 0; x < W; x++) {
      const i = (y * W + x) * 4;
      const k = lum * V.LUX * V.GLASS;                                       // seen through the panes (shadow rays skip them)
      data[i] = col.r * k; data[i + 1] = col.g * k; data[i + 2] = col.b * k; data[i + 3] = 1;
    }
  }
  const t = new THREE.DataTexture(data, W, Hh, THREE.RGBAFormat, THREE.FloatType);
  t.mapping = THREE.EquirectangularReflectionMapping; t.colorSpace = THREE.LinearSRGBColorSpace;
  t.minFilter = t.magFilter = THREE.LinearFilter; t.needsUpdate = true;
  return t;
}

// ---------- the scene for the tracer: the viewer's scene with physical stand-ins ----------
const glassMat = new THREE.MeshPhysicalMaterial({ color: 0xf2f8f6, roughness: 0, metalness: 0, transmission: 1, ior: 1.5, thickness: .004 });
const screenMat = new THREE.MeshPhysicalMaterial({ color: 0x050505, roughness: .03, metalness: 0, clearcoat: 1, clearcoatRoughness: .02 });
let saved = null, running = false, t0 = 0, buildMs = 0, done = false;
function prepare() {
  const S = V.scene, mode = V.mode();
  V.apply();                                                                 // fresh light values for this mode
  saved = { env: S.environment, envI: S.environmentIntensity, bg: S.background, mats: [], vis: [] };
  const hide = o => { saved.vis.push([o, o.visible]); o.visible = false; };
  const show = o => { saved.vis.push([o, o.visible]); o.visible = true; };
  V.wallGroups.forEach(show);                                                // cut-away walls still stop the sun
  hide(V.hemi); V.daylight.forEach(hide);                                    // fake indirect light, sky panel, floor bounce
  // the sun keeps the viewer's intensity (E x glass x LUX): shadow rays pass the panes freely, so their loss is in the light itself
  S.traverse(o => {
    if (!o.isMesh) return;
    const m = o.material;
    if ([m].flat().every(x => x && x.visible === false)) { hide(o); return; }   // the viewer's invisible click boxes (one fills the window)
    if (o.isReflector) { saved.mats.push([o, m]); o.material = screenMat; }
    else if (m?.transparent && m.opacity < .5 && m.isMeshPhysicalMaterial) {
      saved.mats.push([o, m]); o.material = glassMat;
      saved.vis.push([o, o.visible, o.visibleToShadowRays]); o.visibleToShadowRays = false;   // light reaches the room through it
    }
  });
  S.environment = S.background = skyTexture(mode); S.environmentIntensity = 1;
  renderer.toneMappingExposure = V.info().exposure * +$('ptexp').value;      // the viewer's eye adaptation for this mode x a factor
}
function restore() {
  if (!saved) return;
  const S = V.scene;
  saved.mats.forEach(([o, m]) => { o.material = m; });
  saved.vis.forEach(([o, v, sh]) => { o.visible = v; if (sh !== undefined || 'visibleToShadowRays' in o) o.visibleToShadowRays = sh; });
  S.environment.dispose?.(); S.environment = saved.env; S.environmentIntensity = saved.envI; S.background = saved.bg;
  saved = null;
}

async function start() {
  prepare();
  pt.maxSamples = +$('ptspp').value; pt.maxBounces = +$('ptbounce').value;
  const cam = V.camera();
  t0 = performance.now();
  pt.setScene(V.scene, cam);
  buildMs = performance.now() - t0;
  t0 = performance.now(); done = false; running = true;
  canvas.style.display = 'block'; $('ptgo').classList.add('on'); $('ptgo').textContent = 'Выйти из рендера';
  V.renderer.setAnimationLoop(null);                                         // the viewer stops drawing
  document.body.classList.add('pt-on');
}
function stop() {
  running = false; canvas.style.display = 'none';
  $('ptgo').classList.remove('on'); $('ptgo').textContent = 'Рендер';
  restore(); V.apply();
  V.renderer.setAnimationLoop(V.tick);
}
$('ptgo').onclick = () => running ? stop() : start().catch(e => { console.error(e); $('ptstat').textContent = 'Ошибка: ' + e.message; });
$('ptdn').onclick = () => { setDenoise(!denoise); if (running) { pt.reset(); t0 = performance.now(); done = false; } };
$('ptspp').onchange = () => { pt.maxSamples = +$('ptspp').value; if (running) { pt.reset(); t0 = performance.now(); done = false; } };
$('ptbounce').onchange = () => { pt.maxBounces = +$('ptbounce').value; if (running) { pt.reset(); t0 = performance.now(); done = false; } };
$('ptexp').onchange = () => { if (running) { renderer.toneMappingExposure = V.info().exposure * +$('ptexp').value; pt.reset(); t0 = performance.now(); done = false; } };
$('ptsave').onclick = () => { const a = document.createElement('a'); a.download = 'render.png'; a.href = canvas.toDataURL('image/png'); a.click(); };
// the light mode buttons of the viewer: restart the render with the new light
// capture phase: the scene is put back before the viewer's own handler applies the new mode, then the render restarts
document.addEventListener('click', e => {
  if (!running || !e.target.closest?.('[data-light]')) return;
  stop(); setTimeout(() => start(), 0);
}, true);
V.controls.addEventListener('change', () => { if (running) { pt.updateCamera(); t0 = performance.now(); done = false; } });
pt.addEventListener?.('complete', () => { done = true; });
addEventListener('resize', () => { renderer.setSize(innerWidth, innerHeight); if (running) pt.reset(); });

// ---------- loop + stats ----------
let stat = { avg: 0, max: 0, samplesPerSecond: 0 };
setInterval(async () => {
  if (!running) return;
  try { stat = await pt.getSampleCountsAsync(); } catch { /* not ready */ }
  const s = (performance.now() - t0) / 1000;
  $('ptstat').textContent = `${Math.floor(stat.min ?? stat.avg ?? 0)} / ${pt.maxSamples || '∞'} сэмплов · ${s.toFixed(1)} с · `
    + `${Math.round(stat.samplesPerSecond ?? 0)} spp/с · сцена ${Math.round(buildMs)} мс${done ? ' · готово' : ''}`;
  window.__ptStat = { ...stat, seconds: s, buildMs, done };
}, 500);
function loop() {
  requestAnimationFrame(loop);
  if (!running) return;
  V.controls.update();
  pt.renderSample();
}
loop();
