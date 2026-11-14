// ---------- photoreal render mode («Рендер → Фотореалистичный»): path tracing of the viewer's own scene ----------
// three-gpu-pathtracer (WebGPU) + Intel OIDN denoiser, both loaded on the first use. The render goes to a second canvas over the
// viewer's WebGL one; while it is on, the viewer's loop is stopped (the GPU is the tracer's) and its scene is captured with physical
// stand-ins (tools/room3d/pathtrace-spike/README.md explains each):
//  - the viewer's fake light is off (hemisphere = estimated inter-reflections, the sky panel in each window, the floor-patch bounce):
//    the tracer bounces the light itself; a sky environment outside lights the room through the window instead;
//  - meshes the tracer cannot draw are left out: invisible click boxes (one fills the window!), zone overlays (MeshBasicMaterial);
//  - the window panes become real glass that shadow rays pass (their 70 % transmittance is in the sun and the sky);
//  - the TV / oven mirrors (Reflector, a custom shader) become glossy black glass;
//  - camera INSIDE the room: every wall and the ceiling stand (honest light); OUTSIDE: the viewer's cutaway decides the walls and the
//    ceiling goes when the camera is above it (a doll's house: the light leaks in where the walls are cut - shown in the status).
// The viewer calls the hooks around every applyMode (every light change and every build()): the scene is put back before it changes
// and captured again after. Light (stage 3), materials (stage 4), denoiser / resolution / exposure / panel (stages 5-6): below.
while (!window.__viewer?.hooks) await new Promise(r => setTimeout(r, 50));   // the viewer's module awaits the server first
const V = window.__viewer;
const $ = id => document.getElementById(id);
// OIDN weights (Apache 2.0) by denoiser quality: HDR colour + albedo + normal; "small" is faster, "large" (7.7 MB) the cleanest
const OIDN_BASE = 'https://cdn.jsdelivr.net/gh/pissang/oidn-webgpu@main/weights/';
const OIDN_WEIGHTS = { fast: 'rt_hdr_alb_nrm_small.tza', normal: 'rt_hdr_alb_nrm.tza', best: 'rt_hdr_calb_cnrm_large.tza' };
if (navigator.gpu) $('rendersec').hidden = false;                     // no WebGPU, no render mode

// ---------- the render panel (bottom centre while the render is on); the settings are remembered in this browser ----------
const RKEY = 'planner:render';
const DEF = { spp: '256', bounces: '8', scale: '1', motion: 'mid', dn: 'normal', expMode: 'auto', ev: 0, tone: 'neutral', wb: 'auto' };
// detail while the camera moves: the tracer shows a low-resolution preview then, as big as one frame of its work budget allows;
// the budget adapts to a frame time (targetFrameTime) - a longer frame = more pixels in the preview, fewer frames per second
const MOTION = {
  low:  { adaptiveDynamicRes: true,  lowResScale: .1, targetFrameTime: 16, dynamicLowRes: true,  renderDelay: 16 },   // smooth, very soft
  mid:  { adaptiveDynamicRes: false, lowResScale: .5, targetFrameTime: 33, dynamicLowRes: true,  renderDelay: 16 },
  high: { adaptiveDynamicRes: false, lowResScale: 1,  targetFrameTime: 66, dynamicLowRes: true,  renderDelay: 16 },
  full: { adaptiveDynamicRes: false, lowResScale: 1,  targetFrameTime: 100, dynamicLowRes: false, renderDelay: 0 },   // no preview: sharp, jerky
};
let opt = { ...DEF };
try { Object.assign(opt, JSON.parse(localStorage.getItem(RKEY) || '{}')); } catch { /* defaults */ }
const saveOpt = () => { try { localStorage.setItem(RKEY, JSON.stringify(opt)); } catch { /* not kept */ } };
const css = document.createElement('style');
css.textContent = `
  #rcanvas { position:absolute; inset:0; width:100%; height:100%; pointer-events:none; display:none; }
  body.render-on #rcanvas { display:block; }
  body.render-on #c > div { display:none; }                          /* the viewer's labels */
  #rbar { position:fixed; left:50%; bottom:12px; transform:translateX(-50%); z-index:30; display:none; flex-direction:column; gap:6px;
          padding:8px 12px; border-radius:12px; background:var(--sl-panel-background-color, #fff); box-shadow:0 2px 14px rgba(0,0,0,.25);
          font:12px var(--sl-font-sans, system-ui, sans-serif); width:min(880px, calc(100vw - 24px)); box-sizing:border-box; }
  body.render-on #rbar { display:flex; }
  #rbar .rrow { display:flex; flex-wrap:wrap; gap:8px; align-items:flex-end; }
  #rbar sl-select { width:128px; }
  #rbar sl-select::part(form-control-label), #rbar .rlab { font-size:11px; color:var(--sl-color-neutral-600, #666); }
  #rbar .rev { display:flex; flex-direction:column; width:170px; }
  #rbar .rev sl-range { --track-height:4px; }
  #rbar .rbtns { margin-left:auto; display:flex; gap:6px; }
  #rstat { flex:1; min-width:240px; font-variant-numeric:tabular-nums; color:var(--sl-color-neutral-700, #444); }
  #rstat .warn { color:var(--sl-color-warning-700, #a15c00); }
  #rprog { --height:4px; width:100%; }`;
document.head.append(css);
const canvas = Object.assign(document.createElement('canvas'), { id: 'rcanvas' });
V.renderer.domElement.after(canvas);
const bar = Object.assign(document.createElement('div'), { id: 'rbar' });
const sel = (id, label, title, opts) => `<sl-select size="small" id="${id}" label="${label}" hoist title="${title}">`
  + opts.map(([v, t]) => `<sl-option value="${v}">${t}</sl-option>`).join('') + '</sl-select>';
bar.innerHTML = `
  <div class="rrow"><span id="rstat"></span></div>
  <sl-progress-bar id="rprog" value="0"></sl-progress-bar>
  <div class="rrow">
    ${sel('rspp', 'Качество', 'Сколько сэмплов на пиксель накопить: больше — чище и дольше',
      [['32', '32 сэмпла'], ['64', '64 сэмпла'], ['128', '128 сэмплов'], ['256', '256 сэмплов'], ['1024', '1024 сэмпла'], ['0', 'без конца']])}
    ${sel('rbounces', 'Отражения', 'Сколько раз луч отражается: больше — светлее углы и глубже переотражения, медленнее',
      [['4', '4'], ['8', '8'], ['15', '15']])}
    ${sel('rscale', 'Разрешение', 'Разрешение рендера относительно экрана; PNG сохраняется в нём (200 % — вдвое больше экрана)',
      [['0.5', '50 %'], ['0.75', '75 %'], ['1', '100 %'], ['1.5', '150 %'], ['2', '200 %']])}
    ${sel('rmotion', 'При движении', 'Детализация, пока камера движется (поворот, сдвиг, угол обзора): ниже — плавнее, но размыто; выше — чётче, но меньше кадров в секунду',
      [['low', 'низкая, плавно'], ['mid', 'средняя'], ['high', 'высокая'], ['full', 'полная, рывками']])}
    ${sel('rdn', 'Денойзер', 'Intel OIDN дочищает шум после последнего сэмпла. Лучший — чище, но качает 7,7 МБ и считает дольше',
      [['off', 'выключен'], ['fast', 'быстрый'], ['normal', 'обычный'], ['best', 'лучший']])}
  </div>
  <div class="rrow">
    ${sel('rexpmode', 'Экспозиция', 'Авто — по средней яркости кадра, как глаз: подстраивается не полностью, поэтому солнечный день светлее пасмурного, а вечер темнее дня (меряет на 4-м и 32-м сэмпле и в конце); вручную — от экспозиции вьюера',
      [['auto', 'авто'], ['manual', 'вручную']])}
    <div class="rev"><span class="rlab">Поправка, EV: <span id="vev"></span></span>
      <sl-range id="rev" min="-3" max="3" step="0.25" tooltip="none" title="Ступени экспозиции: +1 — вдвое светлее, −1 — вдвое темнее"></sl-range></div>
    ${sel('rtone', 'Тональная кривая', 'Как яркие места сжимаются в белое: Neutral — цвета ближе к настоящим, AgX — как в Blender, мягче пересвет, ACES — кино, контрастнее',
      [['neutral', 'Neutral'], ['agx', 'AgX (Blender)'], ['aces', 'ACES (кино)']])}
    ${sel('rwb', 'Баланс белого', 'Цветовая температура, которую камера считает белой. Авто — по режиму света (солнце 5600 K, пасмурно 6500 K, вечер 3600 K)',
      [['auto', 'авто'], ['2700', '2700 K'], ['3200', '3200 K'], ['4000', '4000 K'], ['5000', '5000 K'], ['5600', '5600 K'], ['6500', '6500 K'], ['8000', '8000 K']])}
    <div class="rbtns">
      <sl-button size="small" id="rpng" title="Сохранить кадр в PNG в разрешении рендера"><sl-icon slot="prefix" name="download"></sl-icon>PNG</sl-button>
      <sl-button size="small" variant="primary" id="rexit" title="Выйти из рендера (Esc)"><sl-icon slot="prefix" name="x-lg"></sl-icon>Выйти</sl-button>
    </div>
  </div>`;
document.body.append(bar);
const ui = { rspp: 'spp', rbounces: 'bounces', rscale: 'scale', rmotion: 'motion', rdn: 'dn', rexpmode: 'expMode', rtone: 'tone', rwb: 'wb' };
Object.entries(ui).forEach(([id, k]) => $(id).setAttribute('value', opt[k]));   // attributes: the Shoelace parts may not be defined yet
$('rev').setAttribute('value', opt.ev);

let W, pt, gpu, OIDN = null;                                        // three/webgpu, the tracer, its renderer, OIDN
const denoisers = {};                                                // one per quality, made on first use
let running = false, saved = null, busy = false, pending = 0, inside = true, t0 = 0, done = false, buildMs = 0, failed = '';
let lastCam = null;
const lastM = new Float64Array(32);                                  // 64-bit: a Float32 copy never equals the matrices again
let WB0 = null;                                                      // the modes' own white balance (for "авто")

async function init() {
  if (pt) return;
  status('Загружаю трассировщик…');
  const [w, P, O] = await Promise.all([import('three/webgpu'), import('three-gpu-pathtracer/webgpu'), import('oidn-webgpu')]);
  W = w; OIDN = { Denoiser: P.OIDNDenoiser, initUNetFromURL: O.initUNetFromURL };
  gpu = new W.WebGPURenderer({ canvas, antialias: false, trackTimestamp: true });   // timestamps: adaptive work per frame
  gpu.setPixelRatio(Math.min(devicePixelRatio, 2));
  await gpu.init();
  pt = new P.WebGPUPathTracer(gpu);
  // filterGlossyFactor: blurs glossy paths a little (fewer fireflies); clampIndirect 0: scene units are lux x 0.01, any clamp
  // would cut the sunlit floor's bounce. The render size is set here (resolution setting), not taken from the canvas.
  Object.assign(pt, { filterGlossyFactor: .5, clampIndirect: 0, synchronizeRenderSize: false });
  pt.addEventListener('complete', () => { done = true; });
  WB0 = Object.fromEntries(Object.entries(V.MODES).map(([k, m]) => [k, m.wb]));
  applyQuality(); applyTone(); applyWB(false);
  new ResizeObserver(fit).observe(V.renderer.domElement);
  fit();
  requestAnimationFrame(loop);
}
function renderSize() {                                              // the drawing buffer x the resolution setting
  const b = gpu.getDrawingBufferSize(new W.Vector2());
  return [Math.max(16, Math.round(b.x * +opt.scale)), Math.max(16, Math.round(b.y * +opt.scale))];
}
function fit() {
  const c = V.renderer.domElement;
  gpu.setSize(c.clientWidth, c.clientHeight, false);
  pt.setSize(...renderSize());
  if (running) restartTimer();
}
function applyQuality() {
  pt.maxSamples = +opt.spp; pt.maxBounces = +opt.bounces;
  Object.assign(pt, MOTION[opt.motion] || MOTION.mid);
  if (opt.dn !== 'off' && !denoisers[opt.dn])
    denoisers[opt.dn] = new OIDN.Denoiser({ initUNetFromURL: OIDN.initUNetFromURL, auxWeightsUrl: OIDN_BASE + OIDN_WEIGHTS[opt.dn] });
  pt.setDenoiser(opt.dn === 'off' ? null : denoisers[opt.dn]);
}
function applyTone() {
  gpu.toneMapping = { neutral: W.NeutralToneMapping, agx: W.AgXToneMapping, aces: W.ACESFilmicToneMapping }[opt.tone] ?? W.NeutralToneMapping;
}
function applyWB(apply = true) {                                     // the camera's white balance = every light's colour in the viewer
  Object.entries(V.MODES).forEach(([k, m]) => { m.wb = opt.wb === 'auto' ? WB0[k] : +opt.wb; });
  if (apply) V.apply();                                              // -> the hooks capture the scene again
}
// ---------- exposure: auto = the meter of a camera - the log-average luminance of the frame's middle 70 % (the brightest and darkest
// 5 % left out: the window must not decide alone) is put near a mid tone (KEY); manual = the viewer's eye adaptation x 0.4. Both x 2^EV.
// Like the viewer's eye, the meter adapts only partly (ADAPT, the viewer's 0.78) around a reference level L_REF: a sunlit room stays
// brighter than an overcast one and an evening darker than a day (a full adaptation made every mode look equally bright).
// Measured log-averages in this room (2026-11-13): sun 0.63, overcast 0.10, evening 0.14 -> sun ~1.5x brighter than overcast on screen.
const KEY = .2, ADAPT = .78, L_REF = .2;
let lastLavg = null;                                                 // the last metered log-average luminance (scene units)
let autoExp = null, meterStage = 0, metering = false;
function exposureValue() {
  const base = opt.expMode === 'auto' && autoExp ? autoExp : V.info.exposure * .4;
  return base * 2 ** +opt.ev;
}
function applyExposure() { if (gpu) gpu.toneMappingExposure = exposureValue(); }
async function meter() {
  const t = pt.target;
  if (!t?.image?.width || metering) return;
  metering = true;
  try {
    const w = t.image.width, h = t.image.height, x0 = Math.floor(w * .15), y0 = Math.floor(h * .15), mw = Math.floor(w * .7), mh = Math.floor(h * .7);
    const buf = await gpu.readRenderTargetPixelsAsync({ textures: [t] }, x0, y0, mw, mh);
    const stride = Math.round(buf.length / mh / 4), logs = [];      // rows may be padded
    let px = 0;
    for (let y = 0; y < mh; y += 3) for (let x = 0; x < mw; x += 3) {
      const i = (y * stride + x) * 4, L = .2126 * buf[i] + .7152 * buf[i + 1] + .0722 * buf[i + 2];
      px++;
      if (Number.isFinite(L) && L > 0) logs.push(Math.log(Math.max(L, 1e-5)));   // 0 = not rendered yet: not metered
    }
    if (logs.length < 16 || logs.length < px * .5) return;            // the frame is not filled yet: keep the last exposure
    logs.sort((a, b) => a - b);
    const lo = logs[Math.floor(logs.length * .05)], hi = logs[Math.floor(logs.length * .95)];
    let s = 0, n = 0;
    for (const v of logs) if (v >= lo && v <= hi) { s += v; n++; }
    lastLavg = Math.exp(s / Math.max(n, 1));
    autoExp = KEY / (lastLavg ** ADAPT * L_REF ** (1 - ADAPT));
    applyExposure();
  } catch (e) { console.warn('exposure meter', e); }
  finally { metering = false; }
}

// ---------- the sky outside: an equirect HDR environment in the viewer's units (cd/m2 x LUX), the camera's white balance in it ----------
// clear  = the Preetham sky model (A. J. Preetham et al., "A Practical Analytic Model for Daylight", 1999) for the sun of the «Солнце»
//          object: dark blue zenith, bright horizon, a glow round the sun; turbidity 3 (a clear day in a town);
// overcast = the CIE overcast sky: zenith 3x the horizon, the same all round;  evening = a faint dark-blue glow (town light).
// Each is scaled so that the sky the window sees has the luminance set on the «Небо в окне» object (the mean over the half of the sky
// in front of the window, as an area light of that luminance would give: the same number the viewer uses), and tinted to its kelvin
// (the model's own variation - bluer zenith, whiter horizon - is kept). Below the horizon: the ground, albedo GROUND, lit by the
// sun and that sky. x GLASS: shadow rays pass the panes, their 70 % is put here.
const TURBIDITY = 3, GROUND = .2;
const lum = c => .2126 * c[0] + .7152 * c[1] + .0722 * c[2];
function preethamSky(sunDir, T) {                                   // -> (dir) => linear sRGB, Y in kcd/m2
  const ts = Math.acos(Math.min(1, Math.max(.02, sunDir.y)));        // sun zenith angle (the sun kept above the horizon)
  const chi = (4 / 9 - T / 120) * (Math.PI - 2 * ts);
  const Yz = (4.0453 * T - 4.9710) * Math.tan(chi) - .2155 * T + 2.4192;
  const t3 = [ts ** 3, ts ** 2, ts, 1], T3 = [T * T, T, 1];
  const mix = M => T3.reduce((a, k, i) => a + k * M[i].reduce((b, m, j) => b + m * t3[j], 0), 0);
  const xz = mix([[.00166, -.00375, .00209, 0], [-.02903, .06377, -.03202, .00394], [.11693, -.21196, .06052, .25886]]);
  const yz = mix([[.00275, -.00610, .00317, 0], [-.04214, .08970, -.04153, .00516], [.15346, -.26756, .06670, .26688]]);
  const coef = {
    Y: [.1787 * T - 1.4630, -.3554 * T + .4275, -.0227 * T + 5.3251, .1206 * T - 2.5771, -.0670 * T + .3703],
    x: [-.0193 * T - .2592, -.0665 * T + .0008, -.0004 * T + .2125, -.0641 * T - .8989, -.0033 * T + .0452],
    y: [-.0167 * T - .2608, -.0950 * T + .0092, -.0079 * T + .2102, -.0441 * T - 1.6537, -.0109 * T + .0529] };
  const F = ([A, B, C, D, E], th, g) => (1 + A * Math.exp(B / Math.max(Math.cos(th), .01))) * (1 + C * Math.exp(D * g) + E * Math.cos(g) ** 2);
  const val = (k, z, th, g) => z * F(coef[k], th, g) / F(coef[k], 0, ts);
  return dir => {
    const th = Math.acos(Math.min(1, Math.max(.001, dir.y))), g = Math.acos(Math.min(1, Math.max(-1, dir.dot(sunDir))));
    const Y = val('Y', Yz, th, g), x = val('x', xz, th, g), y = val('y', yz, th, g);
    const X = x / y * Y, Z = (1 - x - y) / y * Y;
    return [3.2406 * X - 1.5372 * Y - .4986 * Z, -.9689 * X + 1.8758 * Y + .0415 * Z, .0557 * X - .2040 * Y + 1.0570 * Z].map(v => Math.max(0, v));
  };
}
function windowNormal() {                                            // outward normal of the (first) window's wall, three.js coordinates
  const win = V.R.holes.find(h => h.kind === 'window' && h.id === V.envOf('sky')?.window) || V.R.holes.find(h => h.kind === 'window');
  const w = win && V.R.walls.find(w => w.id === win.wall);
  return w ? new W.Vector3(w.nx, 0, -w.ny) : new W.Vector3(-1, 0, 0);
}
function skyTexture(mode) {
  const wb = V.MODES[mode].wb, sky = V.envOf('sky'), sunO = V.envOf('sun');
  const w = 512, h = 256, data = new Float32Array(w * h * 4);
  const sunDir = V.sun.position.clone().sub(V.sun.target.position).normalize();
  const target = mode === 'sun' ? sky?.luminance ?? 5000 : mode === 'cloud' ? sky?.overcast ?? 2500 : .4;   // cd/m2 seen by the window
  const kelvin = mode === 'cloud' ? sky?.kelvin_overcast ?? 6500 : mode === 'sun' ? sky?.kelvin ?? 8000 : 12000;
  const model = mode === 'sun' ? preethamSky(sunDir, TURBIDITY) : d => { const v = (1 + 2 * Math.max(0, d.y)) / 3; return [v, v, v]; };
  // the sky on the grid (relative units), plus what the window sees and what falls on the ground
  const n = windowNormal(), d = new W.Vector3(), sky3 = new Float32Array(w * h * 3);
  let winL = 0, winW = 0, Eh = 0;
  for (let y = h / 2; y < h; y++) {
    const phi = (1 - (y + .5) / h) * Math.PI, sp = Math.sin(phi), dOmega = sp * (Math.PI / h) * (2 * Math.PI / w);
    for (let x = 0; x < w; x++) {
      const th = ((x + .5) / w - .5) * 2 * Math.PI;
      d.set(sp * Math.cos(th), Math.cos(phi), sp * Math.sin(th));
      const c = model(d), i = (y * w + x) * 3, L = lum(c);
      sky3[i] = c[0]; sky3[i + 1] = c[1]; sky3[i + 2] = c[2];
      const cw = d.dot(n);
      if (cw > 0) { winL += L * cw * dOmega; winW += cw * dOmega; }
      Eh += L * d.y * dOmega;
    }
  }
  const scale = winW > 0 && winL > 0 ? target / (winL / winW) : 0;  // relative units -> cd/m2
  // the sky's average colour -> replaced by the object's kelvin (white-balanced like every light), its variation kept
  let ar = 0, ag = 0, ab = 0;
  for (let i = (h / 2) * w * 3; i < sky3.length; i += 3) { ar += sky3[i]; ag += sky3[i + 1]; ab += sky3[i + 2]; }
  const tint = V.lightColor(kelvin, wb), avgL = lum([ar, ag, ab]) || 1;
  const fix = [tint.r * avgL / (ar || 1), tint.g * avgL / (ag || 1), tint.b * avgL / (ab || 1)].map(v => v / lum([tint.r, tint.g, tint.b]));
  const sunE = mode === 'sun' && sunO ? (sunO.illuminance ?? 80000) * Math.max(0, sunDir.y) : 0;
  const groundL = GROUND * (sunE + Eh * scale) / Math.PI;           // a lambertian ground lit by the sun and the sky
  // the ground's own colour: a warm grey (asphalt, trees, houses), lit by the sun's colour (a sunny day) or the sky's
  const gCol = V.lightColor(mode === 'sun' ? sunO?.kelvin ?? 5300 : kelvin, wb).multiply(new W.Color().setRGB(.62, .57, .5, W.SRGBColorSpace));
  const gN = lum([gCol.r, gCol.g, gCol.b]) || 1;
  const k = V.LUX * V.GLASS;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const o = (y * w + x) * 4;
    if (y >= h / 2) {
      const i = (y * w + x) * 3;
      for (let c = 0; c < 3; c++) data[o + c] = sky3[i + c] * fix[c] * scale * k;
    } else {
      data[o] = gCol.r / gN * groundL * k; data[o + 1] = gCol.g / gN * groundL * k; data[o + 2] = gCol.b / gN * groundL * k;
    }
    data[o + 3] = 1;
  }
  const t = new W.DataTexture(data, w, h, W.RGBAFormat, W.FloatType);
  t.mapping = W.EquirectangularReflectionMapping; t.colorSpace = W.LinearSRGBColorSpace;
  t.minFilter = t.magFilter = W.LinearFilter; t.needsUpdate = true;
  return t;
}

// ---------- materials for the render (stage 4): what each surface is made of ----------
// The viewer's materials are flat colours. For the render they are swapped (back after) for physical ones:
//  - the laminate floor: relief (the plank joints and the grain, a normal map made from the floor's own picture) and a roughness
//    that varies with it (joints duller, boards a little glossy);
//  - `finish:` of an object (YAML) - fabric (soft sheen), wood (grain), plastic, paint, satin, gloss, metal, chrome, stone;
//    without it: rug = fabric, slats / portal = wood, walls and ceilings = paint, the rest as it is.
// The object's own colour is kept; a map only modulates it.
const FINISH_BY_TYPE = { rug: 'fabric', slats: 'wood', portal: 'wood' };
const texCache = new Map();
function canvasTexture(key, make, opts = {}) {                      // a generated texture, made once
  if (texCache.has(key)) return texCache.get(key);
  const c = make(), t = new W.CanvasTexture(c);
  t.wrapS = t.wrapT = W.RepeatWrapping; t.colorSpace = opts.color ? W.SRGBColorSpace : W.NoColorSpace; t.anisotropy = 8;
  texCache.set(key, t);
  return t;
}
function heightOf(img, size) {                                       // luminance of a picture as a height field (0..1)
  const c = Object.assign(document.createElement('canvas'), { width: size, height: size }), g = c.getContext('2d');
  g.drawImage(img, 0, 0, size, size);
  const d = g.getImageData(0, 0, size, size).data, h = new Float32Array(size * size);
  for (let i = 0; i < h.length; i++) h[i] = (.2126 * d[i * 4] + .7152 * d[i * 4 + 1] + .0722 * d[i * 4 + 2]) / 255;
  return h;
}
function normalCanvas(h, size, strength) {                           // a tangent-space normal map from a height field (wraps)
  const c = Object.assign(document.createElement('canvas'), { width: size, height: size }), g = c.getContext('2d');
  const out = g.createImageData(size, size), at = (x, y) => h[((y + size) % size) * size + (x + size) % size];
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const dx = (at(x + 1, y) - at(x - 1, y)) * strength, dy = (at(x, y + 1) - at(x, y - 1)) * strength, l = Math.hypot(dx, dy, 1), i = (y * size + x) * 4;
    out.data[i] = (-dx / l * .5 + .5) * 255; out.data[i + 1] = (dy / l * .5 + .5) * 255; out.data[i + 2] = (1 / l * .5 + .5) * 255; out.data[i + 3] = 255;
  }
  g.putImageData(out, 0, 0);
  return c;
}
function laminateMaps(map) {                                         // normal + roughness from the floor's plank picture
  const img = map.image, size = Math.min(1024, img.width || 512), key = 'lam:' + map.uuid;
  const h = heightOf(img, size);
  let lo = 1, hi = 0; h.forEach(v => { lo = Math.min(lo, v); hi = Math.max(hi, v); });
  const normal = canvasTexture(key + ':n', () => normalCanvas(h, size, 6));
  const rough = canvasTexture(key + ':r', () => {
    const c = Object.assign(document.createElement('canvas'), { width: size, height: size }), g = c.getContext('2d'), o = g.createImageData(size, size);
    for (let i = 0; i < h.length; i++) {                             // dark = a joint: dull; light board: a little glossier
      const r = .62 - .28 * (h[i] - lo) / Math.max(hi - lo, 1e-3);
      o.data[i * 4 + 1] = r * 255; o.data[i * 4 + 3] = 255;          // three.js reads roughness from the green channel
    }
    g.putImageData(o, 0, 0); return c;
  });
  [normal, rough].forEach(t => { t.repeat.copy(map.repeat); t.offset.copy(map.offset); t.rotation = map.rotation; t.center.copy(map.center); });
  return { normal, rough };
}
function woodMaps() {                                                // straight-grained wood along the texture's v (a board's length)
  const N = 512;
  let seed = 11; const rnd = () => (seed = seed * 16807 % 2147483647) / 2147483647;
  const ph = Array.from({ length: 6 }, () => rnd() * 6.28);
  const grain = (x, y) => {                                          // 0..1: rings across u, slowly wavering along v
    const u = x / N, v = y / N, w = .035 * Math.sin(v * 6.28 * 2 + ph[0]) + .02 * Math.sin(v * 6.28 * 5 + ph[1]);
    const ring = Math.sin((u + w) * 6.28 * 7 + 3 * Math.sin(u * 6.28 + ph[2]));
    const fine = Math.sin((u + w * .5) * 6.28 * 60 + ph[3]) * .5 + Math.sin(v * 6.28 * 90 + u * 40) * .15;
    return Math.min(1, Math.max(0, .55 + .35 * ring * ring * Math.sign(ring) + .08 * fine));
  };
  const h = new Float32Array(N * N);
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) h[y * N + x] = grain(x, y);
  const color = canvasTexture('wood:c', () => {                      // near white, darker late wood: multiplies the object's colour
    const c = Object.assign(document.createElement('canvas'), { width: N, height: N }), g = c.getContext('2d'), o = g.createImageData(N, N);
    for (let i = 0; i < h.length; i++) { const v = (.72 + .28 * h[i]) * 255; o.data[i * 4] = v; o.data[i * 4 + 1] = v * .97; o.data[i * 4 + 2] = v * .93; o.data[i * 4 + 3] = 255; }
    g.putImageData(o, 0, 0); return c;
  }, { color: true });
  const normal = canvasTexture('wood:n', () => normalCanvas(h, N, 2.5));
  return { color, normal };
}
function rugMaps(map) {                                              // the weave: a fine relief from the rug's own picture
  const size = Math.min(1024, map.image.width || 512), h = heightOf(map.image, size);
  const n = canvasTexture('rug:' + map.uuid, () => normalCanvas(h, size, 4));
  n.repeat.copy(map.repeat); n.offset.copy(map.offset);
  return n;
}
const FINISH = {                                                     // physical presets: what the material gets on top of its colour
  fabric:  m => ({ roughness: Math.max(m.roughness, .9), metalness: 0, sheen: 1, sheenRoughness: .55,
                   sheenColor: m.color.clone().lerp(new W.Color(1, 1, 1), .35), specularIntensity: .4 }),
  wood:    () => { const w = woodMaps(); return { map: w.color, normalMap: w.normal, normalScale: new W.Vector2(.6, .6), roughness: .5, metalness: 0 }; },
  plastic: () => ({ roughness: .42, metalness: 0, specularIntensity: .7 }),
  paint:   () => ({ roughness: .9, metalness: 0, specularIntensity: .5 }),
  satin:   () => ({ roughness: .35, metalness: 0, clearcoat: .3, clearcoatRoughness: .3 }),
  gloss:   () => ({ roughness: .2, metalness: 0, clearcoat: 1, clearcoatRoughness: .05 }),
  metal:   () => ({ roughness: .32, metalness: 1 }),
  chrome:  () => ({ roughness: .05, metalness: 1 }),
  stone:   () => ({ roughness: .3, metalness: 0, clearcoat: .2, clearcoatRoughness: .2 }),
};
const matCache = new WeakMap();                                      // original material -> its render version (per finish)
function physical(m, extra) {                                        // a MeshPhysicalMaterial with m's own look + extra
  const p = new W.MeshPhysicalMaterial({
    color: m.color, map: m.map, roughness: m.roughness, metalness: m.metalness, normalMap: m.normalMap, roughnessMap: m.roughnessMap,
    emissive: m.emissive, emissiveIntensity: m.emissiveIntensity, emissiveMap: m.emissiveMap, transparent: m.transparent,
    opacity: m.opacity, alphaMap: m.alphaMap, side: m.side, clearcoat: m.clearcoat || 0, clearcoatRoughness: m.clearcoatRoughness || 0 });
  if (m.normalScale) p.normalScale.copy(m.normalScale);
  return Object.assign(p, extra);
}
function renderMaterial(o, m) {                                      // the render version of mesh o's material m, or null (keep m)
  if (!m?.isMeshStandardMaterial || m.transparent) return null;
  let p = o; while (p && !p.userData.id) p = p.parent;
  const id = p?.userData.id, obj = id && [...V.R.objects, ...(V.R.apartment || []).flatMap(r => r.objects)].find(x => x.id === id);
  const finish = obj?.finish || FINISH_BY_TYPE[obj?.type] || (id?.startsWith('w:') || m === V.ceilMat ? 'paint' : null);
  const floor = !id && m.map?.isCanvasTexture && !finish;            // the laminate (a floor has no id)
  if (!finish && !floor) return null;
  const key = floor ? 'laminate' : finish;
  let byKey = matCache.get(m);
  if (!byKey) matCache.set(m, byKey = {});
  if (byKey[key]) return byKey[key];
  let r;
  if (floor) { const l = laminateMaps(m.map); r = physical(m, { normalMap: l.normal, normalScale: new W.Vector2(.8, .8), roughnessMap: l.rough, roughness: 1, specularIntensity: .8 }); }
  else {
    r = physical(m, FINISH[finish](m));
    if (finish === 'fabric' && m.map?.isCanvasTexture) { r.normalMap = rugMaps(m.map); r.normalScale = new W.Vector2(.7, .7); }
  }
  return byKey[key] = r;
}

// ---------- capturing the viewer's scene for the tracer ----------
let glassMat, screenMat;
function cameraInside() {                                            // in the room's outline (plan) and under its ceiling
  const p = V.camera.position, x = p.x / V.S, y = -p.z / V.S, z = p.y / V.S, pts = V.R.walls.map(w => w.a);
  let inPlan = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inPlan = !inPlan;
  }
  return inPlan && z > 0 && z < V.H;
}
function prepare() {
  glassMat ||= new W.MeshPhysicalMaterial({ color: 0xf7f9f8, roughness: 0, metalness: 0, transmission: 1, ior: 1.5, thickness: .004 });
  screenMat ||= new W.MeshPhysicalMaterial({ color: 0x050505, roughness: .03, metalness: 0, clearcoat: 1, clearcoatRoughness: .02 });
  const S = V.scene, above = V.camera.position.y / V.S >= V.H;
  inside = cameraInside();
  saved = { env: S.environment, envI: S.environmentIntensity, bg: S.background, mats: [], vis: [], added: [] };
  const set = (o, v) => { saved.vis.push([o, 'visible', o.visible]); o.visible = v; };
  const prop = (o, k, v) => { saved.vis.push([o, k, o[k]]); o[k] = v; };
  const exposure = exposureValue();
  if (inside) V.wallGroups.forEach(g => set(g, true));               // every wall stops the sun
  else V.updateWalls();                                              // a doll's house: the cutaway for this camera
  set(V.hemi, false); V.daylight.forEach(l => set(l, false));        // fake indirect light, sky panel, floor bounce
  // the sun: a disk of its true size (0.53 deg) far away instead of a parallel light, so shadows get the real soft edge.
  // Its luminance makes the same illuminance: E = L x solid angle. (sun.intensity = E x glass x LUX, as in the viewer.)
  if (V.sun.visible && V.sun.intensity > 0) {
    const dir = V.sun.position.clone().sub(V.sun.target.position).normalize(), D = 300, a = SUN_RADIUS;
    const disk = new W.RectAreaLight(V.sun.color, V.sun.intensity / (2 * Math.PI * (1 - Math.cos(a))), 2 * D * Math.tan(a), 2 * D * Math.tan(a));
    disk.isCircular = true;
    disk.position.copy(V.sun.target.position).addScaledVector(dir, D); disk.lookAt(V.sun.target.position);
    S.add(disk); disk.updateMatrixWorld(); saved.added.push(disk);
    set(V.sun, false);
  }
  // lamps: an emitter of real size (soft shadows); the bulb's point light (no size in the tracer) -> two half-sphere spots of the
  // globe's radius; the glowing parts (downlight lenses, strip diffusers, the bulb's glass) let their own light through and glow
  // as bright as a lit lamp looks, whatever the exposure
  const lensMats = new Set();
  V.lamps.forEach(l => {
    if (!l.visible) return;
    const lens = l.userData.lens;
    lensMats.add(lens); prop(lens, 'emissiveIntensity', LAMP_GLOW / exposure);
    if (l.isSpotLight) prop(l, 'radius', DOWNLIGHT_RADIUS);
    if (l.isPointLight) {
      set(l, false);
      [-1, 1].forEach(sy => {
        const s = new W.SpotLight(l.color, l.intensity, 0, Math.PI / 2 * .999, 0, 2);
        s.radius = BULB_RADIUS; s.position.copy(l.position); s.target.position.copy(l.position).add(new W.Vector3(0, sy, 0));
        l.parent.add(s, s.target); s.updateMatrixWorld(); s.target.updateMatrixWorld(); saved.added.push(s, s.target);
      });
    }
  });
  S.traverse(o => {
    if (!o.isMesh || !o.visible) return;
    const m = o.material, ms = [m].flat();
    if (lensMats.has(m)) prop(o, 'visibleToShadowRays', false);
    if (o.isReflector) { saved.mats.push([o, m]); o.material = screenMat; return; }
    if (ms.every(x => x?.visible === false) || !ms.every(x => x?.isMeshStandardMaterial)) { set(o, false); return; }   // click boxes, zones
    if (m === V.ceilMat && !inside && above) { set(o, false); return; }
    if (m.transparent && m.opacity < .5 && m.isMeshPhysicalMaterial) {   // window panes
      saved.mats.push([o, m]); o.material = glassMat;
      saved.vis.push([o, 'visibleToShadowRays', o.visibleToShadowRays]); o.visibleToShadowRays = false;
    }
    else if (!Array.isArray(m)) {                                      // what the surface is made of (stage 4)
      const r = renderMaterial(o, m);
      if (r) { saved.mats.push([o, m]); o.material = r; }
    }
  });
  S.environment = S.background = skyTexture(V.mode); S.environmentIntensity = 1;
  gpu.toneMappingExposure = exposure;                                // auto: the last metered value until the meter runs again
}
const SUN_RADIUS = .2665 * Math.PI / 180;                            // the sun's angular radius
const DOWNLIGHT_RADIUS = .03, BULB_RADIUS = .03;                     // m: a downlight's lens, an A60 bulb's globe
const LAMP_GLOW = 6;                                                 // a lit lamp's glass on screen: well over white (scene units after exposure)
function restore() {
  if (!saved) return;
  const S = V.scene;
  saved.mats.forEach(([o, m]) => { o.material = m; });
  saved.added.forEach(o => { o.removeFromParent(); o.dispose?.(); });
  for (let i = saved.vis.length - 1; i >= 0; i--) { const [o, k, v] = saved.vis[i]; o[k] = v; }   // backwards: the first value wins
  S.environment?.dispose?.();
  S.environment = saved.env; S.environmentIntensity = saved.envI; S.background = saved.bg;
  saved = null;
}
function capture() {                                                 // (re)build the tracer's copy of the scene
  pending = 0;
  if (!running) return;
  busy = true;
  try {
    restore(); prepare();
    const t = performance.now();
    pt.setScene(V.scene, V.camera);
    buildMs = performance.now() - t;
    lastCam = V.camera; failed = '';
  } catch (e) { console.error(e); failed = e.message; }
  finally { busy = false; }
  restartTimer();
}
function recapture() { if (running && !pending) pending = setTimeout(capture, 120); }   // after a burst of edits: once
function restartTimer() { t0 = performance.now(); done = false; meterStage = 0; resetGen++; }
let resetGen = 0;                                                    // +1 on every restart: sample counts read before it are stale

// the viewer's applyMode: before = put the scene back (it is about to change it), after = capture it again
V.hooks.beforeLight.push(() => { if (running && !busy) restore(); });
V.hooks.afterLight.push(() => { if (running && !busy) recapture(); });

// ---------- on / off ----------
async function start() {
  if (running) return;
  try { await init(); }
  catch (e) { console.error(e); status('Не удалось запустить трассировщик: ' + e.message); return; }
  running = true;
  document.body.classList.add('render-on');
  V.renderer.setAnimationLoop(null);                                 // the viewer stops drawing
  // no orbit inertia while rendering: the camera stops when the mouse does, so the samples start piling up at once
  // (with damping it drifted for ~1 s after every move, and each drifting frame restarted the accumulation)
  damping = V.controls.enableDamping; V.controls.enableDamping = false;
  capture();
}
let damping = true;
function stop() {
  if (!running) return;
  running = false; clearTimeout(pending); pending = 0;
  restore();
  document.body.classList.remove('render-on');
  V.controls.enableDamping = damping;
  V.apply();                                                         // the viewer's own light again
  V.renderer.setAnimationLoop(V.tick);
}
$('brender').addEventListener('click', () => running ? stop() : start());
V.renderMode = { get pt() { return pt; }, get running() { return running; }, get inside() { return inside; }, canvas, start, stop, skyTexture,
  get exposure() { return gpu?.toneMappingExposure; }, get opt() { return opt; }, get restarts() { return restarts; }, get lavg() { return lastLavg; } };   // console / tests
$('rexit').addEventListener('click', stop);
addEventListener('keydown', e => { if (running && e.key === 'Escape' && !e.target.closest?.('sl-select')) stop(); });
const resetPT = () => { if (running) { pt.reset(); restartTimer(); } };
const onOpt = (id, fn) => $(id).addEventListener('sl-change', () => { opt[ui[id] || id] = $(id).value; saveOpt(); if (pt) fn(); });
onOpt('rspp', () => { applyQuality(); resetPT(); });
onOpt('rbounces', () => { applyQuality(); resetPT(); });
onOpt('rmotion', () => applyQuality());                              // only the next move looks different
onOpt('rdn', () => { applyQuality(); resetPT(); });
onOpt('rscale', () => { fit(); });
onOpt('rexpmode', () => { applyExposure(); if (opt.expMode === 'auto') { meterStage = 0; } });   // no new samples needed
onOpt('rtone', () => applyTone());
onOpt('rwb', () => applyWB());
const evLabel = () => { $('vev').textContent = (opt.ev > 0 ? '+' : '') + (+opt.ev).toFixed(2).replace(/\.?0+$/, '').replace('.', ','); };
evLabel();
$('rev').addEventListener('sl-input', () => { opt.ev = +$('rev').value; evLabel(); applyExposure(); });
$('rev').addEventListener('sl-change', () => saveOpt());
// PNG in the render's own resolution: the canvas is resized to it for one frame (the tracer does not follow the canvas size here),
// read right after that frame is drawn (a WebGPU canvas keeps its picture only until it is presented) and put back
let saveRequest = false;
$('rpng').addEventListener('click', () => { saveRequest = true; });
function savePng() {
  saveRequest = false;
  const [w, h] = renderSize(), c = V.renderer.domElement, pr = gpu.getPixelRatio();
  gpu.setSize(w / pr, h / pr, false);
  pt.renderSample();
  canvas.toBlob(b => {
    if (!b) return;
    const a = Object.assign(document.createElement('a'), { download: `render-${w}x${h}-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.png`,
      href: URL.createObjectURL(b) });
    a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  }, 'image/png');
  gpu.setSize(c.clientWidth, c.clientHeight, false);
}

// ---------- loop: the camera is followed (a move restarts the accumulation) ----------
// Crossing into / out of the room changes the walls, i.e. the scene has to be captured again (BVH, a pause): that is checked only
// once the camera has stood still for SETTLE ms, so orbiting through a wall does not stall the render on every crossing.
const SETTLE = 350;
let movedAt = 0, restarts = 0;                                       // restarts: camera moves seen (console / tests)
function loop() {
  requestAnimationFrame(loop);
  if (!running || pending || !saved) return;
  V.controls.update();
  const cam = V.camera, now = performance.now();
  cam.updateMatrixWorld();
  if (cam !== lastCam) { recapture(); return; }                      // perspective <-> orthographic
  const m = [...cam.matrixWorld.elements, ...cam.projectionMatrix.elements];
  // a real move, not round-off: OrbitControls.update() recomputes the position through spherical coordinates every call and can
  // land a last bit off - compared exactly, that restarted the accumulation again and again (stuck at 0 samples, no denoiser)
  if (m.some((v, i) => Math.abs(v - lastM[i]) > 1e-7 * Math.max(1, Math.abs(v)))) {
    restarts++;
    lastM.set(m); movedAt = now;
    pt.updateCamera(); restartTimer();
  } else if (movedAt && now - movedAt > SETTLE) {
    movedAt = 0;
    if (cameraInside() !== inside) { recapture(); return; }
  }
  if (saveRequest) savePng(); else pt.renderSample();
}

// ---------- status line + progress; the exposure meter runs from here (on the 4th and 32nd sample and once finished) ----------
function status(text) { $('rstat').innerHTML = text; }
setInterval(async () => {
  if (!running || !pt) return;
  if (failed) return status(`<span class="warn">Ошибка: ${failed}</span>`);
  if (pending || !saved) { $('rprog').indeterminate = true; return status('Готовлю сцену…'); }
  let c = {};
  const gen = resetGen;
  try { c = await pt.getSampleCountsAsync(); } catch { /* not ready yet */ }
  if (gen !== resetGen) return;                                      // counted before a restart: stale
  const n = Math.floor(c.min ?? 0), max = pt.maxSamples, s = (performance.now() - t0) / 1000;
  if (opt.expMode === 'auto' && !metering && (meterStage === 0 && n >= 4 || meterStage === 1 && n >= 32 || meterStage === 2 && done)) { meterStage++; meter(); }
  $('rprog').indeterminate = false; $('rprog').value = max ? Math.min(100, n / max * 100) : 0;
  const [w, h] = renderSize(), ev = Math.log2(exposureValue() / (V.info.exposure * .4));
  status(`${n} / ${max || '∞'} сэмплов · ${s.toFixed(1)} с · ${Math.round(c.samplesPerSecond ?? 0)} сэмпл/с · ${w}×${h}`
    + ` · экспозиция ${ev >= 0 ? '+' : ''}${ev.toFixed(1).replace('.', ',')} EV${opt.expMode === 'auto' ? ' (авто)' : ''}`
    + (done ? (pt._denoiser ? ' · готово, денойзер' : ' · готово') : '')
    + (inside ? '' : ' · <span class="warn" title="Камера снаружи комнаты: срезанные стены и потолок пропускают свет. Для честного света поставьте камеру внутрь.">камера снаружи — свет приблизительный</span>'));
}, 400);
