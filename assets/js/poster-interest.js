(() => {
  const cfgEl = document.querySelector('script.pi-config');
  if (!cfgEl) return;
  let cfg;
  try { cfg = JSON.parse(cfgEl.textContent); }
  catch (e) { console.warn('[poster-interest] bad config:', e.message); return; }

  const endpoint = (cfg.endpoint || '').trim();          // empty = dry run
  const themes = Array.isArray(cfg.themes) ? cfg.themes : [];
  const sizes  = Array.isArray(cfg.sizes)  ? cfg.sizes  : [];
  if (!sizes.length && !themes.length) {
    console.warn('[poster-interest] no themes or sizes configured');
    return;
  }

  const STORE_NONCE = 'poster-interest:nonce';
  const STORE_SENT  = 'poster-interest:sent';

  // A random per-browser id so repeat submissions can be collapsed server-side.
  // It identifies a browser to itself, never a person.
  const nonce = (() => {
    try {
      let n = localStorage.getItem(STORE_NONCE);
      if (!n) {
        n = (crypto.randomUUID && crypto.randomUUID()) ||
            String(Date.now()) + Math.random().toString(36).slice(2);
        localStorage.setItem(STORE_NONCE, n);
      }
      return n;
    } catch { return 'anon'; }                           // storage blocked: still works
  })();

  const alreadySent = () => {
    try { return JSON.parse(localStorage.getItem(STORE_SENT) || '[]'); }
    catch { return []; }
  };
  const markSent = (key) => {
    try {
      const all = alreadySent();
      if (!all.includes(key)) all.push(key);
      localStorage.setItem(STORE_SENT, JSON.stringify(all.slice(-20)));
    } catch {}
  };

  // ---- build the dialog (never authored in the page: see the include's note)
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;              // textContent, never innerHTML
    return n;
  };

  const dlg = el('dialog', 'pi-modal');
  const form = el('form', 'pi-form');
  form.noValidate = true;

  const close = el('button', 'pi-close', '×');
  close.type = 'button';
  close.setAttribute('aria-label', 'Close');
  form.appendChild(close);

  form.appendChild(el('h2', 'pi-title', cfg.title || 'Interested in a poster?'));
  if (cfg.blurb) form.appendChild(el('p', 'pi-blurb', cfg.blurb));

  let themeEl = null, costEl = null;

  const currency = cfg.currency || '$';
  const costOf = (id) => {
    const s = sizes.find(x => x.id === id);
    return s && s.cost != null ? Number(s.cost) : null;
  };
  const currentSize = () => {
    const picked = document.querySelector('.pi-chip input:checked');
    return picked ? picked.value : '';
  };
  const updateCost = () => {
    if (!costEl) return;
    const c = costOf(currentSize());
    if (c == null) { costEl.textContent = ''; costEl.hidden = true; return; }
    costEl.hidden = false;
    costEl.textContent = currency + c + (cfg.costNote ? ' \u00b7 ' + cfg.costNote : '');
  };
  if (themes.length) {
    const field = el('div', 'pi-field');
    const lab = el('label', 'pi-label', cfg.themeLabel || 'Theme');
    lab.htmlFor = 'pi-theme';
    themeEl = el('select', 'pi-select');
    themeEl.id = 'pi-theme';
    themeEl.name = 'theme';
    // no pre-selected theme: whichever set sorts first would otherwise become
    // the default answer and skew the signal
    if (cfg.themePlaceholder) {
      const ph = el('option', null, cfg.themePlaceholder);
      ph.value = '';
      ph.disabled = true;
      ph.selected = true;
      themeEl.appendChild(ph);
    }
    for (const t of themes) {
      const o = el('option', null, t.label || t.id);
      o.value = t.id;
      themeEl.appendChild(o);
    }
    field.append(lab, themeEl);
    form.appendChild(field);
  }

  if (sizes.length) {
    const fs = el('fieldset', 'pi-field pi-sizes');
    fs.appendChild(el('legend', 'pi-label', cfg.sizeLabel || 'Size'));
    const chips = el('div', 'pi-chips');
    sizes.forEach((s, i) => {
      const wrap = el('label', 'pi-chip');
      const input = document.createElement('input');
      input.type = 'radio';
      input.name = 'size';
      input.value = s.id;
      if (i === 0) input.checked = true;
      wrap.append(input, el('span', null, s.label || s.id));
      chips.appendChild(wrap);
    });
    fs.appendChild(chips);
    form.appendChild(fs);

    // running estimate for the selected size, when costs are configured
    if (sizes.some(s => s.cost != null)) {
      costEl = el('p', 'pi-cost');
      fs.appendChild(costEl);
      chips.addEventListener('change', updateCost);
    }
  }

  if (cfg.noteLabel) {
    const field = el('div', 'pi-field');
    const lab = el('label', 'pi-label', cfg.noteLabel);
    lab.htmlFor = 'pi-note';
    const noteEl = el('textarea', 'pi-note');
    noteEl.id = 'pi-note';
    noteEl.name = 'note';
    noteEl.rows = 2;
    noteEl.maxLength = 240;
    noteEl.placeholder = cfg.notePlaceholder || '';
    field.append(lab, noteEl);
    form.appendChild(field);
  }

  // honeypot: real people never see or fill this
  const hp = el('div', 'pi-hp');
  hp.setAttribute('aria-hidden', 'true');
  const hpInput = document.createElement('input');
  hpInput.type = 'text';
  hpInput.name = 'website';
  hpInput.tabIndex = -1;
  hpInput.autocomplete = 'off';
  const hpLabel = el('label', null, 'Website');
  hpLabel.appendChild(hpInput);
  hp.appendChild(hpLabel);
  form.appendChild(hp);

  const actions = el('div', 'pi-actions');
  const cancel = el('button', 'pi-cancel', 'Cancel');
  cancel.type = 'button';
  const submit = el('button', 'pi-submit', 'Send');
  submit.type = 'submit';
  actions.append(cancel, submit);
  form.appendChild(actions);

  const status = el('p', 'pi-status');
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  status.hidden = true;
  form.appendChild(status);

  dlg.appendChild(form);
  document.body.appendChild(dlg);
  updateCost();

  // ---- behaviour
  const setStatus = (msg, kind) => {
    status.textContent = msg || '';
    status.hidden = !msg;
    status.className = 'pi-status' + (kind ? ' is-' + kind : '');
  };

  const reset = () => {
    setStatus('');
    submit.disabled = false;
    submit.textContent = 'Send';
    form.classList.remove('is-done');
  };

  for (const btn of document.querySelectorAll('.pi-open')) {
    btn.addEventListener('click', () => {
      reset();
      if (btn.dataset.theme && themeEl) {
        const opt = [...themeEl.options].find(o => o.value === btn.dataset.theme);
        if (opt) themeEl.value = opt.value;
      }
      dlg.showModal();
    });
  }
  close.addEventListener('click', () => dlg.close());
  cancel.addEventListener('click', () => dlg.close());
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = new FormData(form);

    if ((data.get('website') || '').trim()) {            // honeypot tripped
      form.classList.add('is-done');                     // look successful, send nothing
      setStatus(cfg.thanks || 'Noted — thank you.', 'ok');
      return;
    }

    const payload = {
      v: 1,
      nonce,
      theme: data.get('theme') || '',
      size:  data.get('size')  || '',
      note:  (data.get('note') || '').slice(0, 240),
      // the figure actually shown, so rows stay interpretable after a price change
      cost:  costOf(data.get('size') || ''),
      currency,
      page:  location.pathname,
      ts:    new Date().toISOString(),
    };

    if (themeEl && !payload.theme) {
      setStatus('Pick a theme first.', 'err');
      themeEl.focus();
      return;
    }

    const key = payload.theme + '|' + payload.size;
    if (alreadySent().includes(key)) {
      form.classList.add('is-done');
      setStatus("You've already flagged that one — it's counted.", 'ok');
      return;
    }

    submit.disabled = true;
    submit.textContent = 'Sending…';
    setStatus('');

    if (!endpoint) {                                     // dry run
      console.log('[poster-interest] dry run, would POST:', payload);
      await new Promise(r => setTimeout(r, 400));
      markSent(key);
      form.classList.add('is-done');
      setStatus('Dry run — payload logged to the console.', 'ok');
      return;
    }

    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 8000);
      const r = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: ctrl.signal,
      });
      clearTimeout(t);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      markSent(key);
      form.classList.add('is-done');
      setStatus(cfg.thanks || 'Noted — thank you.', 'ok');
    } catch (err) {
      submit.disabled = false;
      submit.textContent = 'Try again';
      setStatus("That didn't go through. Please try again in a moment.", 'err');
      console.warn('[poster-interest]', err.message);
    }
  });
})();
