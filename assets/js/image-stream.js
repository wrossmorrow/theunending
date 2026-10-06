(() => {
  // ---------------------------------------------------------------- shared
  const syncs = [];              // every stream's clock gate on this page
  let modalOpen = false;         // while true, no stream advances
  const syncAll = () => syncs.forEach(f => f());
  const metaCache = new Map();

  // ---------------------------------------------------------------- modal
  let dlg = null;
  const ensureModal = () => {
    if (dlg) return dlg;
    dlg = document.createElement('dialog');
    dlg.className = 'is-modal';
    dlg.innerHTML = `
      <button class="is-modal-close" aria-label="Close">&times;</button>
      <figure class="is-modal-figure">
        <img class="is-modal-img" alt="">
        <figcaption class="is-modal-meta" hidden></figcaption>
      </figure>`;
    document.body.appendChild(dlg);
    const fig = dlg.querySelector('.is-modal-figure');
    const bigImg = dlg.querySelector('.is-modal-img');
    // the caption/strip matches the image's RENDERED width, which depends on
    // whether max-width or max-height is the binding constraint -> measure it
    const sizeToImage = () => {
      const w = bigImg.getBoundingClientRect().width;
      if (w) fig.style.setProperty('--img-w', w + 'px');
    };
    bigImg.addEventListener('load', () => requestAnimationFrame(sizeToImage));
    window.addEventListener('resize', () => { if (dlg.open) sizeToImage(); });
    dlg.querySelector('.is-modal-close').addEventListener('click', () => dlg.close());
    // <dialog> makes its own backdrop: a click landing on the element itself is outside
    dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
    dlg.addEventListener('close', () => { modalOpen = false; syncAll(); });
    return dlg;
  };

  const loadMeta = async (src, id) => {
    if (!src.meta) return null;
    try {
      if (src.meta.includes('{id}')) {                  // one small file per image
        const r = await fetch(src.meta.replace('{id}', encodeURIComponent(id)));
        return r.ok ? await r.json() : null;
      }
      if (!metaCache.has(src.meta)) {                   // one map for the whole set
        metaCache.set(src.meta, fetch(src.meta).then(r => r.ok ? r.json() : {}).catch(() => ({})));
      }
      return (await metaCache.get(src.meta))[id] || null;
    } catch { return null; }
  };

  const thumbUrl = (src, id) => src.base + id + src.ext;
  const largeUrl = (src, id) => (src.largeBase || src.base) + id + src.ext;

  // `lookup(id)` resolves a neighbour id to its own source, so a pooled strip
  // can show similars that live under a different prefix than the clicked image
  const renderMeta = (el, meta, id, src, lookup) => {
    el.textContent = '';
    const frag = document.createDocumentFragment();
    if (meta && meta.title) {
      const h = document.createElement('h2');
      h.className = 'is-modal-title';
      h.textContent = meta.title;           // textContent, never innerHTML
      frag.appendChild(h);
    }
    const dl = document.createElement('dl');
    for (const [k, v] of Object.entries(meta || {})) {
      if (k === 'title' || k === 'similar' || v == null || v === '') continue;
      const dt = document.createElement('dt'); dt.textContent = k;
      const dd = document.createElement('dd'); dd.textContent = String(v);
      dl.append(dt, dd);
    }
    if (dl.children.length) frag.appendChild(dl);

    // nearest neighbours, precomputed offline: ["uuid", ...] or [{id, score}, ...]
    const sim = Array.isArray(meta && meta.similar) ? meta.similar : [];
    if (sim.length) {
      const wrap = document.createElement('div');
      wrap.className = 'is-modal-similar';
      const lab = document.createElement('div');
      lab.className = 'is-modal-similar-label';
      lab.textContent = 'similar';
      wrap.appendChild(lab);
      const row = document.createElement('div');
      row.className = 'is-modal-similar-row';
      row.style.setProperty('--ar', src.ratio || 1);
      for (const entry of sim.slice(0, 8)) {
        const nid = typeof entry === 'string' ? entry : (entry && entry.id);
        if (!nid) continue;
        const nsrc = (lookup && lookup(nid)) || src;
        const b = document.createElement('button');
        b.className = 'is-modal-thumb';
        b.type = 'button';
        const score = typeof entry === 'object' && entry.score != null
          ? Number(entry.score).toFixed(3) : null;
        b.title = score ? `${nid} (${score})` : nid;
        b.setAttribute('aria-label', 'Show similar image');
        const im = document.createElement('img');
        im.loading = 'lazy';
        im.alt = '';
        im.src = thumbUrl(nsrc, nid);
        b.appendChild(im);
        b.addEventListener('click', () => showImage(nid, nsrc, lookup));
        row.appendChild(b);
      }
      if (row.children.length) {
        row.style.setProperty('--sim-n', row.children.length);
        wrap.appendChild(row);
        frag.appendChild(wrap);
      }
    }

    const foot = document.createElement('p');
    foot.className = 'is-modal-id';
    const a = document.createElement('a');
    a.href = largeUrl(src, id); a.target = '_blank'; a.rel = 'noopener';
    a.textContent = id.length > 60 ? 'open original' : id;
    foot.appendChild(a);
    frag.appendChild(foot);
    el.appendChild(frag);
    el.hidden = false;
  };

  // swap the modal to another image without closing it (used by the similar tiles)
  let showToken = 0;
  const showImage = (id, src, lookup) => {
    const d = ensureModal();
    const token = ++showToken;                 // ignore a slow meta fetch we've moved past
    const img = d.querySelector('.is-modal-img');
    const metaEl = d.querySelector('.is-modal-meta');
    metaEl.hidden = true;
    metaEl.textContent = '';
    img.src = largeUrl(src, id);
    loadMeta(src, id).then(m => {
      if (token === showToken) renderMeta(metaEl, m, id, src, lookup);
    });
  };

  const openModal = (id, src, lookup) => {
    const d = ensureModal();
    modalOpen = true;
    syncAll();                           // freeze every stream on the page
    showImage(id, src, lookup);
    d.showModal();
  };

  // ---------------------------------------------------------------- stream
  const initStream = (root) => {
    if (root.dataset.isInit) return;          // safe if the include appears twice
    root.dataset.isInit = '1';
    const d = root.dataset;
    const axis = d.axis === 'x' ? 'x' : 'y';  // 'x' = a single horizontal ticker
    const cfg = {
      base:      d.base || '',
      largeBase: d.largeBase || d.base || '',  // full-size variant, if you have one
      meta:      d.meta || '',                 // URL, optionally containing {id}
      manifest:  d.manifest || '',
      ext:       d.ext ?? '',
      interval:  +(d.interval || 1000),
      cols:      +(d.cols || 5),
      rows:      axis === 'x' ? 1 : +(d.rows || 4),
      ratio:     +(d.ratio || 1),              // tile width / height
      shuffle:   d.shuffle !== 'false',
      // column range: colsMin === colsMax means fixed, and no picker is shown
      colsMin:   +(d.colsMin || d.cols || 5),
      colsMax:   +(d.colsMax || d.cols || 5),
      targetTile:+(d.targetTile || 200),       // px: desired tile width for the auto default
      setKey:    d.set || d.base || 'default',
      controls:  d.controls !== 'false',
      theater:   d.theater !== 'false',        // show the theater button
      theaterInterval: +(d.theaterInterval || 0),   // 0 = keep the normal cadence
      theaterTargetTile: +(d.theaterTargetTile || d.targetTile || 200),
      axis,
    };
    cfg.colsMax = Math.max(cfg.colsMax, cfg.colsMin);
    cfg.cols = Math.max(cfg.colsMin, Math.min(cfg.colsMax, cfg.cols));
    root.style.setProperty('--cols', cfg.cols);
    root.style.setProperty('--rows', cfg.rows);
    root.style.setProperty('--ar', cfg.ratio);

    const viewport = document.createElement('div');
    viewport.className = 'is-viewport';
    const track = document.createElement('div');
    track.className = 'is-track';
    track.dataset.axis = axis;
    viewport.appendChild(track);
    root.appendChild(viewport);

    // how many cells leave per shift, and when a shift is due
    const perShift = () => (axis === 'x' ? 1 : cfg.cols);
    const capacity = () => cfg.rows * cfg.cols;

    // ---- geometry
    let theaterOn = false;
    let shifting = false;
    let cellW = 0, cellH = 0, gap = 0;
    const measure = () => {
      const cs = getComputedStyle(track);
      gap = parseFloat(axis === 'x' ? cs.columnGap : cs.rowGap) || 0;
      const w = viewport.clientWidth;
      cellW = (w - gap * (cfg.cols - 1)) / cfg.cols;
      cellH = cellW / cfg.ratio;
      if (theaterOn && axis === 'y') {
        // inverted from the normal case: the height is given, so derive rows
        // from it rather than deriving the height from a fixed row count
        const availH = root.clientHeight || window.innerHeight;
        cfg.rows = Math.max(1, Math.floor((availH + gap) / (cellH + gap)));
        root.style.setProperty('--rows', cfg.rows);
        viewport.style.height = availH + 'px';
      } else {
        viewport.style.height = (cfg.rows * cellH + (cfg.rows - 1) * gap) + 'px';
      }
    };
    measure();

    // ---- column count: auto from the container width, or the viewer's choice
    const STORE = 'img-stream:cols:' + cfg.setKey;
    const readPref = () => {
      try {
        const v = +localStorage.getItem(STORE);
        return v >= cfg.colsMin && v <= cfg.colsMax ? v : null;
      } catch { return null; }                       // private mode, blocked storage
    };
    const writePref = (n) => { try { localStorage.setItem(STORE, String(n)); } catch {} };
    const clearPref = () => { try { localStorage.removeItem(STORE); } catch {} };
    let manual = readPref() !== null;

    const autoCols = () => {
      const w = viewport.clientWidth || root.clientWidth || 800;
      const n = Math.round(w / cfg.targetTile) || cfg.colsMin;
      return Math.max(cfg.colsMin, Math.min(cfg.colsMax, n));
    };

    let controlsEl = null;
    const applyCols = (n) => {
      n = Math.max(cfg.colsMin, Math.min(cfg.colsMax, n));
      if (n === cfg.cols) { updateControls(); return; }
      cfg.cols = n;
      root.style.setProperty('--cols', n);
      track.style.transition = 'none';               // abandon any in-flight shift
      track.style.transform = 'none';
      shifting = false;
      measure();
      while (track.children.length > capacity()) track.firstChild.remove();
      updateControls();
    };

    const updateControls = () => {
      if (!controlsEl) return;
      for (const b of controlsEl.querySelectorAll('.is-colbtn')) {
        const on = +b.dataset.n === cfg.cols;
        b.classList.toggle('is-on', on);
        b.setAttribute('aria-pressed', String(on));
      }
      const auto = controlsEl.querySelector('.is-colauto');
      if (auto) auto.hidden = !manual;
    };

    const buildControls = () => {
      if (!cfg.controls || cfg.colsMax <= cfg.colsMin) return;
      controlsEl = document.createElement('div');
      controlsEl.className = 'is-controls';
      const lab = document.createElement('span');
      lab.className = 'is-controls-label';
      lab.textContent = 'columns';
      controlsEl.appendChild(lab);
      for (let n = cfg.colsMin; n <= cfg.colsMax; n++) {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'is-colbtn';
        b.dataset.n = n;
        b.textContent = n;
        b.setAttribute('aria-label', n + ' columns');
        b.addEventListener('click', () => { manual = true; writePref(n); applyCols(n); });
        controlsEl.appendChild(b);
      }
      const auto = document.createElement('button');
      auto.type = 'button';
      auto.className = 'is-colauto';
      auto.textContent = 'auto';
      auto.hidden = true;
      auto.addEventListener('click', () => { manual = false; clearPref(); applyCols(autoCols()); });
      controlsEl.appendChild(auto);
      root.appendChild(controlsEl);                  // sits under the grid
    };

    const buildTheaterBtn = () => {
      if (!cfg.theater || axis === 'x') return;      // a one-row ticker has nothing to expand
      if (!controlsEl) {
        controlsEl = document.createElement('div');
        controlsEl.className = 'is-controls';
        root.appendChild(controlsEl);
      }
      theaterBtn = document.createElement('button');
      theaterBtn.type = 'button';
      theaterBtn.className = 'is-theaterbtn';
      theaterBtn.textContent = 'theater mode';
      theaterBtn.addEventListener('click', () => theaterOn ? exitTheater() : enterTheater());
      controlsEl.appendChild(theaterBtn);
    };

    // ---- theater mode
    // CSS does the work (position:fixed, inset:0). The Fullscreen API is an
    // enhancement on top: iOS Safari won't fullscreen a non-video element, and
    // fullscreening the *stream* would leave the <dialog> (a child of body)
    // outside the fullscreen subtree -- so when it is available we fullscreen
    // the document element instead, and the modal keeps working.
    let theaterBtn = null, savedRows = cfg.rows, savedInterval = cfg.interval;
    let savedTarget = cfg.targetTile, savedManual = manual;

    const retime = () => {                            // restart the clock at a new interval
      if (timer) { clearInterval(timer); timer = null; }
      sync();
    };

    const enterTheater = () => {
      if (theaterOn) return;
      theaterOn = true;
      savedRows = cfg.rows; savedInterval = cfg.interval;
      savedTarget = cfg.targetTile; savedManual = manual;
      if (cfg.theaterInterval) cfg.interval = cfg.theaterInterval;
      cfg.targetTile = cfg.theaterTargetTile;
      manual = false;                                 // let the wider viewport choose
      root.classList.add('is-theater');
      document.body.classList.add('is-theater-open');
      if (document.documentElement.requestFullscreen) {
        document.documentElement.requestFullscreen().catch(() => {});
      }
      applyCols(autoCols());
      measure();
      retime();
      const short = capacity() - track.children.length;
      if (short > 0) fill(short, 90);                // top up to the new capacity
      if (theaterBtn) theaterBtn.textContent = 'exit';
      window.addEventListener('keydown', onKey);
    };

    const exitTheater = () => {
      if (!theaterOn) return;
      theaterOn = false;
      cfg.rows = savedRows; cfg.interval = savedInterval;
      cfg.targetTile = savedTarget; manual = savedManual;
      root.classList.remove('is-theater');
      document.body.classList.remove('is-theater-open');
      root.style.setProperty('--rows', cfg.rows);
      if (document.fullscreenElement && document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
      }
      applyCols(manual ? readPref() : autoCols());
      measure();
      while (track.children.length > capacity()) track.firstChild.remove();
      retime();
      if (theaterBtn) theaterBtn.textContent = 'theater mode';
      window.removeEventListener('keydown', onKey);
    };

    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      if (document.querySelector('dialog[open]')) return;   // modal eats this one
      exitTheater();
    };
    // leaving fullscreen by any route (Esc, browser UI) must also leave theater
    document.addEventListener('fullscreenchange', () => {
      if (!document.fullscreenElement && theaterOn) exitTheater();
    });

    new ResizeObserver(() => {
      if (!manual) applyCols(autoCols());            // no-op when the count is unchanged
      measure();
    }).observe(viewport);

    // ---- sources: one per set, each with its own base/ext/meta
    const defaultSrc = {
      base: cfg.base, largeBase: cfg.largeBase, ext: cfg.ext,
      meta: cfg.meta, ratio: cfg.ratio,
    };
    const urlFor   = (e) => e.src.base + e.id + e.src.ext;
    const shuffled = (a) => {
      const x = a.slice();
      for (let i = x.length - 1; i > 0; i--) {
        const j = (Math.random() * (i + 1)) | 0;
        [x[i], x[j]] = [x[j], x[i]];
      }
      return x;
    };

    let ids = [], order = [], cursor = 0;
    const byId = new Map();                          // id -> src, for modal neighbours
    const lookup = (id) => byId.get(id) || null;

    const nextEntry = () => {
      if (cursor >= order.length) {                  // endless: reshuffle each pass
        order = cfg.shuffle ? shuffled(ids) : ids.slice();
        cursor = 0;
      }
      return order[cursor++];
    };

    // ---- preload one ahead so tiles never pop in blank
    let ahead = null;
    const preload = () => {
      const e = nextEntry();
      if (e === undefined) return null;
      const img = new Image();
      img.decoding = 'async';
      img.loading = 'eager';
      img.alt = '';
      img.src = urlFor(e);
      return { entry: e, img, ready: img.decode().catch(() => 'error') };
    };

    // ---- scrolling
    const shift = () => {
      if (shifting) return;
      // move as many units as we are over capacity, so a slide slower than the
      // tick interval catches up instead of letting the track grow
      const over = track.children.length - capacity();
      const units = Math.max(1, Math.ceil(over / perShift()));
      shifting = true;
      const step = axis === 'x' ? cellW + gap : cellH + gap;
      const dist = units * step;
      const t = axis === 'x' ? `translateX(${-dist}px)` : `translateY(${-dist}px)`;
      track.style.transition = `transform var(--slide) cubic-bezier(.4,0,.2,1)`;
      track.style.transform = t;
      let settled = false, fallback = null;
      const done = () => {
        if (settled) return;                          // transitionend + fallback can race
        settled = true;
        clearTimeout(fallback);
        track.removeEventListener('transitionend', done);
        for (let i = 0; i < units * perShift() && track.firstChild; i++) track.firstChild.remove();
        track.style.transition = 'none';
        track.style.transform = 'none';
        void track.offsetHeight;                      // flush, avoid a visible jump
        shifting = false;
      };
      if (getComputedStyle(root).getPropertyValue('--slide').trim() === '0ms') done();
      else {
        track.addEventListener('transitionend', done);
        // a transition that never runs (unrendered tab, interrupted paint) would
        // otherwise latch `shifting` forever and the removal would never happen
        fallback = setTimeout(done, 1500);
      }
    };

    // place a batch quickly (first paint, and when theater enlarges the grid)
    const fill = (n, step) => {
      let left = n;
      const t = setInterval(() => {
        place();
        if (--left <= 0) { clearInterval(t); sync(); }
      }, step);
    };

    const place = async () => {
      if (!ahead) ahead = preload();
      if (!ahead) return;
      const { entry, img, ready } = ahead;
      ahead = null;
      const res = await ready;
      if (res === 'error') { ahead = preload(); return; }   // skip bad key, try next tick

      const cell = document.createElement('div');
      cell.className = 'is-cell';
      cell.dataset.id = entry.id;
      cell.tabIndex = 0;
      cell.setAttribute('role', 'button');
      cell.setAttribute('aria-label', 'Open image');
      cell.appendChild(img);
      track.appendChild(cell);
      requestAnimationFrame(() => img.classList.add('is-in'));

      if (track.children.length > capacity()) shift();
      // backstop: never let the track grow without bound, whatever went wrong
      const cap = capacity() + 2 * cfg.cols;
      while (track.children.length > cap) track.firstChild.remove();
      ahead = preload();
    };

    // ---- open on click / Enter / Space (delegated: cells come and go)
    const openFrom = (cell) => {
      const id = cell.dataset.id;
      openModal(id, lookup(id) || defaultSrc, lookup);
    };
    track.addEventListener('click', (e) => {
      const cell = e.target.closest('.is-cell');
      if (cell) openFrom(cell);
    });
    track.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      const cell = e.target.closest('.is-cell');
      if (cell) { e.preventDefault(); openFrom(cell); }
    });

    // ---- clock: paused when offscreen, tab hidden, or a modal is open
    let timer = null, visible = true, onscreen = true;
    const sync = () => {
      const run = visible && onscreen && !modalOpen && ids.length > 0;
      if (run && !timer) timer = setInterval(place, cfg.interval);
      if (!run && timer) { clearInterval(timer); timer = null; }
    };
    syncs.push(sync);
    document.addEventListener('visibilitychange', () => {
      visible = !document.hidden; sync();
    });
    new IntersectionObserver(
      ([e]) => { onscreen = e.isIntersecting; sync(); },
      { threshold: 0 }
    ).observe(root);

    buildControls();
    buildTheaterBtn();
    applyCols(manual ? readPref() : autoCols());

    // ---- load the id list.
    // Preferred: <script class="is-sources"> holding [{base, ext, meta, ids|manifest}, ...]
    // so one stream can pool several sets. Falls back to the single-set shapes:
    // <script class="is-manifest"> or data-manifest, accepting
    // ["uuid",...] | {images:[...]} | [{id:"uuid"},...]
    const idsOf = (j) => {
      const arr = Array.isArray(j) ? j : (j.images || j.ids || j.keys || []);
      return arr.map(x => (typeof x === 'string' ? x : (x && (x.id || x.key || x.name))))
                .filter(Boolean);
    };

    const sourcesEl = root.querySelector('script.is-sources');
    const inlineEl  = root.querySelector('script.is-manifest');
    let plan;
    if (sourcesEl) {
      const defs = JSON.parse(sourcesEl.textContent) || [];
      plan = Promise.all(defs.map(def => {
        const src = {
          base:      def.base ?? cfg.base,
          largeBase: def.largeBase ?? def.base ?? cfg.largeBase,
          ext:       def.ext ?? cfg.ext,
          meta:      def.meta ?? '',
          ratio:     def.ratio ?? cfg.ratio,
        };
        const got = def.ids
          ? Promise.resolve(def.ids)
          : fetch(def.manifest, { cache: 'no-cache' })
              .then(r => { if (!r.ok) throw new Error(def.manifest + ': ' + r.status); return r.json(); })
              .catch(e => { console.warn('[img-stream]', e.message); return []; });
        return got.then(j => idsOf(j).map(id => ({ id, src })));
      })).then(lists => lists.flat());
    } else {
      const got = inlineEl
        ? Promise.resolve(JSON.parse(inlineEl.textContent))
        : fetch(cfg.manifest, { cache: 'no-cache' })
            .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
      plan = got.then(j => idsOf(j).map(id => ({ id, src: defaultSrc })));
    }

    plan
      .then(entries => {
        ids = entries;
        if (!ids.length) throw new Error('empty list');
        for (const e of ids) byId.set(e.id, e.src);
      })
      .catch(err => {
        console.warn('[img-stream] no usable image list, using demo tiles:', err.message);
        const src = { base: '', largeBase: '', ext: '', meta: '', ratio: cfg.ratio };
        ids = demoTiles(60).map(id => ({ id, src }));
      })
      .finally(() => {
        // fill the first screen quickly, then settle into the steady cadence
        fill(capacity(), Math.min(120, cfg.interval));
      });
  };

  // placeholder tiles so the file previews standalone; delete in production
  const demoTiles = (n) => Array.from({ length: n }, (_, i) => {
    const c = document.createElement('canvas');
    c.width = c.height = 120;
    const ctx = c.getContext('2d');
    const g = ctx.createLinearGradient(0, 0, 120, 120);
    const h = (i * 37) % 360;
    g.addColorStop(0, `hsl(${h} 55% 45%)`);
    g.addColorStop(1, `hsl(${(h + 60) % 360} 55% 25%)`);
    ctx.fillStyle = g; ctx.fillRect(0, 0, 120, 120);
    ctx.fillStyle = 'rgba(255,255,255,.75)';
    ctx.font = '600 13px system-ui'; ctx.textAlign = 'center';
    ctx.fillText(String(i + 1), 60, 65);
    return c.toDataURL('image/png');
  });

  const boot = () => document.querySelectorAll('.img-stream').forEach(initStream);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
