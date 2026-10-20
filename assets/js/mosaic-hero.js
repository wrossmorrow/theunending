(() => {
  const root = document.querySelector('.mosaic');
  if (!root) return;

  const cfgEl = document.querySelector('script.mosaic-config');
  let cfg = {};
  try { cfg = JSON.parse(cfgEl.textContent); }
  catch (e) { console.warn('[mosaic] bad config:', e.message); return; }

  const TILE     = cfg.tile     || 210;    // target tile edge in px
  const SWAP_MS  = cfg.swapMs   || 620;    // average gap between swaps
  const FADE_MS  = cfg.fadeMs   || 900;
  const MAX_LOAD = cfg.maxLoads || 3;      // concurrent image fetches

  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  root.style.setProperty('--fade', FADE_MS + 'ms');

  // ---- pool -------------------------------------------------------------
  // One flat list across every set, so what you see is the whole project
  // rather than one theme at a time.

  const shuffle = (a) => {
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  };

  // Images are drawn per set rather than from one flat shuffled list.
  //
  // A flat pool looks random but isn't evenly spread: with low-variance sets
  // (the masks, the sockets, Load Bearing) three draws from one set land on
  // screen together and read as the same picture repeated, which is the
  // opposite of what a landing page full of everything should say. Dealing
  // round-robin and then always refilling from the least-represented set
  // keeps every set on screen roughly equally.
  let bySet = {};        // name -> { src, ids, cur }
  let setNames = [];
  let live = {};         // name -> tiles currently showing it

  const flatten = (sets) => {
    bySet = {};
    live = {};
    for (const [set, s] of Object.entries(sets || {})) {
      const ids = (s.ids || []).slice();
      if (!ids.length) continue;
      const ext = s.ext || 'png';
      bySet[set] = { ids: shuffle(ids), cur: 0, ext, base: s.base };
      live[set] = 0;
    }
    setNames = shuffle(Object.keys(bySet));
    return setNames.length;
  };

  // the hover caption, so you can tell where a tile goes before clicking it
  const label = (cell, item) => {
    cell.dataset.label = nameFor(item.set);
    cell.classList.toggle('is-linked', !!(infoFor(item.set) || {}).url);
  };

  const nextFrom = (set) => {
    const s = bySet[set];
    const id = s.ids[s.cur++ % s.ids.length];
    return { set, id, src: `${s.base}${id}.${s.ext}` };
  };

  // least represented on screen right now; ties broken at random so the
  // refill order never settles into a pattern
  const thinnestSet = (avoid) => {
    let best = Infinity, pick = [];
    for (const name of setNames) {
      if (name === avoid && setNames.length > 1) continue;
      const n = live[name];
      if (n < best) { best = n; pick = [name]; }
      else if (n === best) pick.push(name);
    }
    return pick[(Math.random() * pick.length) | 0];
  };

  // ---- grid -------------------------------------------------------------
  let cols = 0, rows = 0, cells = [], inflight = 0, timer = null;

  const build = () => {
    const c = Math.max(2, Math.round(innerWidth / TILE));
    const edge = innerWidth / c;
    const r = Math.max(2, Math.ceil(innerHeight / edge));
    if (c === cols && r === rows && cells.length) return;
    cols = c; rows = r;
    root.style.setProperty('--cols', cols);
    root.style.setProperty('--rows', rows);

    root.replaceChildren();
    cells = [];
    const total = cols * rows;
    for (let i = 0; i < total; i++) {
      const cell = document.createElement('button');
      cell.type = 'button';
      cell.className = 'mo-cell';
      cell.tabIndex = -1;                  // see the a11y note below
      const a = document.createElement('img');
      const b = document.createElement('img');
      for (const img of [a, b]) {
        img.className = 'mo-img';
        img.alt = '';
        img.decoding = 'async';
        img.draggable = false;
      }
      a.classList.add('is-on');
      cell.append(a, b);

      const item = nextFrom(setNames[i % setNames.length]);
      live[item.set]++;
      a.src = item.src;
      label(cell, item);
      cell._front = a; cell._back = b; cell._item = item;
      cell.addEventListener('click', () => activate(cell._item));
      root.appendChild(cell);
      cells.push(cell);
    }
  };

  // ---- swapping ---------------------------------------------------------
  // Paused whenever the tab is in the background (otherwise this quietly
  // downloads images forever in a tab nobody is looking at), while a modal
  // is open, and entirely when reduced motion is requested.
  const paused = () =>
    document.hidden || document.querySelector('dialog[open]') !== null;

  const swapOne = () => {
    if (paused() || inflight >= MAX_LOAD || !cells.length) return;

    const cell = cells[(Math.random() * cells.length) | 0];
    if (!cell || cell._busy) return;

    const prev = cell._item.set;
    const item = nextFrom(thinnestSet(prev));
    if (item.src === cell._item.src) return;
    live[prev]--; live[item.set]++;

    cell._busy = true;
    inflight++;
    const back = cell._back;

    const give = () => { inflight--; cell._busy = false; };

    const reveal = () => {
      inflight--;
      back.classList.add('is-on');
      cell._front.classList.remove('is-on');
      // swap the layer roles only after the fade, or the next swap on this
      // cell would yank the image out from under a transition in progress
      setTimeout(() => {
        const front = cell._front;
        cell._front = back;
        cell._back = front;
        cell._item = item;
        label(cell, item);
        cell._busy = false;
      }, FADE_MS + 60);
    };

    back.src = item.src;
    if (back.decode) back.decode().then(reveal).catch(give);
    else { back.onload = reveal; back.onerror = give; }
  };

  const tick = () => {
    swapOne();
    // jittered, so swaps never fall into a visible rhythm
    timer = setTimeout(tick, SWAP_MS * (0.6 + Math.random() * 0.8));
  };

  const start = () => { if (!reduce && !timer) tick(); };
  const stop  = () => { clearTimeout(timer); timer = null; };

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stop(); else start();
  });

  let rt = null;
  addEventListener('resize', () => {
    clearTimeout(rt);
    rt = setTimeout(build, 180);
  });

  // ---- what a tile does -------------------------------------------------
  // It goes to that image's set. Not a modal: a modal on a landing page is a
  // side door that keeps you on the landing page, competing with the only
  // thing the page is for. This way the whole field is the navigation and
  // Enter is just the unspecific version of it.
  const setUrls = cfg.setUrls || {};

  // Accepts either {set: "/url/"} or {set: {url, title}} so an older cached
  // config does not break the page while a build rolls out.
  const infoFor = (set) => {
    const v = setUrls[set];
    if (!v) return null;
    return typeof v === 'string' ? { url: v, title: null } : v;
  };

  // only a fallback now: the set key is a slug with disambiguating suffixes,
  // the post title is the name meant to be read
  const pretty = (name) =>
    name.replace(/[-_]+/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

  const nameFor = (set) => {
    const info = infoFor(set);
    return (info && info.title) || pretty(set);
  };

  function activate(item) {
    const info = infoFor(item.set);
    if (info && info.url) location.href = info.url;
  }

  // ---- go ---------------------------------------------------------------
  const init = (sets) => {
    if (!flatten(sets)) { console.warn('[mosaic] empty pool'); return; }
    build();
    start();
  };

  if (cfg.sets) {
    init(cfg.sets);
  } else if (cfg.poolUrl) {
    fetch(cfg.poolUrl, { cache: 'no-cache' })
      .then(r => r.json())
      .then(d => init(d.sets))
      .catch(e => console.warn('[mosaic] pool fetch failed:', e.message));
  }
})();
