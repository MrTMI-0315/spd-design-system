/* Shared SPD UI kit: 9-patch chrome, sprites, buttons, toast, tooltip, slider, zoom.
   Pages await window.SPD_UI, which resolves once chrome.png has been cut into 9-patches. */
window.SPD_UI = (async () => {
  const T = window.SPD;
  const C = 'core/src/main/java/com/shatteredpixel/shatteredpixeldungeon/';
  const W = 'SPD-classes/src/main/java/com/watabou/';
  const $ = (s) => document.querySelector(s);

  function h(tag, attrs = {}, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null) continue;
      if (k === 'class') el.className = v;
      else if (k === 'style') el.style.cssText = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v);
    }
    for (const kid of kids.flat()) if (kid != null) el.append(kid);
    return el;
  }

  const ghURL = (src) => {
    const [path, line] = src.split(':');
    return `https://github.com/00-Evan/shattered-pixel-dungeon/blob/${T.meta.commit.hash}/${path}${line ? '#L' + line : ''}`;
  };
  const shortSrc = (src) => src.replace(C, '').replace(W, '');
  const srcLink = (src) => h('a', { class: 'src', href: ghURL(src), target: '_blank', rel: 'noopener' }, shortSrc(src));
  const prov = (label, inferred) => h('span', { class: 'prov' + (inferred ? ' inf' : '') }, label);

  /* ---------------- zoom ---------------- */
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } },
  };
  let zoom = Number(store.get('spd-zoom')) || (innerWidth < 720 ? 2 : 3);
  document.documentElement.style.setProperty('--z', zoom);

  /* ---------------- sprites & 9-patch ---------------- */
  const SHEETS = {
    icons: ['assets/icons.png', 256, 128],
    buffs: ['assets/buffs.png', 128, 64],
    large_buffs: ['assets/large_buffs.png', 256, 128],
    toolbar: ['assets/toolbar.png', 256, 32],
    status_pane: ['assets/status_pane.png', 128, 128],
    rat: ['assets/rat.png', 256, 64],
  };
  function sprite(sheet, [x, y, w, hh], label) {
    const [url, sw, sh] = SHEETS[sheet];
    return h('span', {
      class: 'spr', role: label ? 'img' : null, 'aria-label': label || null, 'aria-hidden': label ? null : 'true',
      style: `--x:${x};--y:${y};--w:${w};--h:${hh};--sw:${sw};--sh:${sh};background-image:url(${url})`,
    });
  }
  const ICON = Object.fromEntries(T.icons.items.map((i) => [i.name, i]));
  const icon = (name, label) => sprite('icons', ICON[name].rect, label);

  const CH = Object.fromEntries(T.chrome.types.map((t) => [t.name, t]));
  const sheetImg = new Image();
  sheetImg.src = window.SPD_CHROME_PNG;
  await sheetImg.decode();
  const chromeURL = {};
  for (const t of T.chrome.types) {
    const [x, y, w, hh] = t.rect;
    const cv = h('canvas', { width: w, height: hh });
    cv.getContext('2d').drawImage(sheetImg, x, y, w, hh, 0, 0, w, hh);
    chromeURL[t.name] = cv.toDataURL();
  }
  function chrome(el, name) {
    const [l, t, r, b] = CH[name].margins;
    el.classList.add('ch');
    el.style.setProperty('--ml', l); el.style.setProperty('--mt', t);
    el.style.setProperty('--mr', r); el.style.setProperty('--mb', b);
    el.style.borderImageSource = `url("${chromeURL[name]}")`;
    el.style.borderImageSlice = `${t} ${r} ${b} ${l} fill`;
    return el;
  }
  const bg = (name) => chrome(h('span', { class: 'bg', 'aria-hidden': 'true' }), name);

  /* ---------------- shared components ---------------- */
  function button(label, { chromeName = 'RED_BUTTON', size = 9, height = 20, disabled = false, onclick, iconName, pressed } = {}) {
    const b = h('button', {
      class: 'btn', type: 'button', style: `--bh:${height};font-size:calc(${size} * var(--u))`,
      'aria-disabled': disabled ? 'true' : null, 'aria-pressed': pressed == null ? null : String(pressed),
      onclick: (e) => { if (!disabled && onclick) onclick(e); },
    }, bg(chromeName), iconName ? icon(iconName) : null, label ? h('span', { class: 'lbl' }, label) : null);
    return b;
  }

  // Toast (TOAST_TR + Icons.CLOSE)
  const toastHost = $('#toast-host');
  let toastTimer;
  function toast(text) {
    toastHost.replaceChildren(h('div', { class: 'toast t6' }, bg('TOAST_TR'), h('span', {}, text), icon('CLOSE')));
    toastHost.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toastHost.hidden = true; }, 1600);
  }
  async function copy(text, what) {
    try { await navigator.clipboard.writeText(text); toast(`${what} 복사됨`); }
    catch { toast('복사할 수 없습니다'); }
  }

  // Tooltip: Tooltip.java alpha starts at -5 and rises 10/s -> visible after 0.5s, full at 0.6s.
  // Shown again within 0.25s of the last one, it skips the delay.
  const tip = chrome($('#tooltip'), 'TOAST_TR_HEAVY');
  let tipTimer, tipHiddenAt = -1;
  document.addEventListener('pointerover', (e) => {
    const target = e.target.closest('[data-tip]');
    if (!target) return;
    const show = () => {
      tip.textContent = target.dataset.tip;
      const r = target.getBoundingClientRect();
      tip.style.left = Math.min(innerWidth - tip.offsetWidth - 8, Math.max(8, r.left)) + 'px';
      tip.style.top = (r.bottom + 6) + 'px';
      tip.classList.add('show');
    };
    clearTimeout(tipTimer);
    if (performance.now() - tipHiddenAt < 250) show(); else tipTimer = setTimeout(show, 500);
  });
  document.addEventListener('pointerout', (e) => {
    const target = e.target.closest('[data-tip]');
    if (!target || target.contains(e.relatedTarget)) return;
    clearTimeout(tipTimer);
    if (tip.classList.contains('show')) tipHiddenAt = performance.now();
    tip.classList.remove('show');
  });

  // OptionSlider
  function slider(title, min, max, value, oninput, fmt = String) {
    const knob = chrome(h('span', { class: 'knob' }), 'RED_BUTTON');
    const track = h('span', { class: 'track' });
    for (let i = 0; i <= max - min; i++) track.append(h('span', { class: 'tick', style: `left:${(i / (max - min)) * 100}%` }));
    track.append(knob);
    const input = h('input', { type: 'range', min, max, step: 1, value, 'aria-label': title });
    const ttl = h('span', { class: 'ttl' });
    const root = h('div', { class: 'slider' }, bg('RED_BUTTON'), ttl, track,
      h('span', { class: 'lo' }, fmt(min)), h('span', { class: 'hi' }, fmt(max)), input);
    const sync = () => {
      const v = Number(input.value);
      knob.style.left = ((v - min) / (max - min)) * 100 + '%';
      ttl.textContent = `${title}: ${fmt(v)}`;
      oninput(v);
    };
    input.addEventListener('input', sync);
    input.addEventListener('pointerdown', () => root.classList.add('drag'));
    addEventListener('pointerup', () => root.classList.remove('drag'));
    sync();
    return root;
  }

  /* ---------------- zoom control ---------------- */
  function zoomControl(container) {
    const render = () => container.replaceChildren(...[2, 3, 4].map((z) =>
      button(`×${z}`, { size: 7, height: 16, pressed: z === zoom, onclick: () => { zoom = z; document.documentElement.style.setProperty('--z', z); store.set('spd-zoom', z); render(); } })));
    render();
  }

  return { T, C, W, $, h, ghURL, shortSrc, srcLink, prov, store, SHEETS, sprite, ICON, icon, CH, chrome, bg, button, toast, copy, slider, zoomControl, zoom: () => zoom };
})();
