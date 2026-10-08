(() => {
  const cfgEl = document.querySelector('script.idea-config');
  if (!cfgEl) return;
  let cfg;
  try { cfg = JSON.parse(cfgEl.textContent); }
  catch (e) { console.warn('[prompt-idea] bad config:', e.message); return; }

  const endpoint = (cfg.endpoint || '').trim();          // empty = dry run
  const NAME_MAX = cfg.nameMax || 60;
  const BODY_MAX = cfg.bodyMax || 256;
  const BODY_MIN = cfg.bodyMin || 12;
  const CONTACT_MAX = cfg.contactMax || 120;

  const STORE_NONCE = 'prompt-idea:nonce';
  const STORE_SENT = 'prompt-idea:sent';

  // A random per-browser id. It identifies a browser to itself, never a person,
  // and it is what the server's soft daily quota counts against.
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

  // Cheap non-cryptographic hash, only ever compared against itself. It exists
  // so resubmitting the same idea is caught locally instead of at the server.
  const hash = (s) => {
    let h = 5381;
    for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
    return (h >>> 0).toString(36);
  };
  const normalize = (s) => s.trim().toLowerCase().replace(/\s+/g, ' ');

  const alreadySent = () => {
    try { return JSON.parse(localStorage.getItem(STORE_SENT) || '[]'); }
    catch { return []; }
  };
  const markSent = (key) => {
    try {
      const all = alreadySent();
      if (!all.includes(key)) all.push(key);
      localStorage.setItem(STORE_SENT, JSON.stringify(all.slice(-40)));
    } catch {}
  };

  // ---- build the dialog (never authored in the page: see the include's note)
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;              // textContent, never innerHTML
    return n;
  };

  const dlg = el('dialog', 'idea-modal');
  const form = el('form', 'idea-form');
  form.noValidate = true;                                // we report errors ourselves

  const close = el('button', 'idea-close', '×');
  close.type = 'button';
  close.setAttribute('aria-label', 'Close');
  form.appendChild(close);

  form.appendChild(el('h2', 'idea-head', cfg.title || 'Have a prompt idea?'));
  if (cfg.blurb) form.appendChild(el('p', 'idea-blurb', cfg.blurb));

  // A labelled field with a live character counter.
  const field = (id, label, max, { multiline = false, placeholder = '', rows = 4 } = {}) => {
    const wrap = el('div', 'idea-field');
    const lab = el('label', 'idea-label', label);
    lab.htmlFor = id;

    const input = multiline ? el('textarea', 'idea-input idea-area')
                            : el('input', 'idea-input');
    if (!multiline) input.type = 'text';
    else input.rows = rows;
    input.id = id;
    input.maxLength = max;
    input.placeholder = placeholder;
    input.autocomplete = 'off';

    const count = el('span', 'idea-count', '0/' + max);
    const sync = () => {
      count.textContent = input.value.length + '/' + max;
      count.classList.toggle('is-full', input.value.length >= max);
    };
    input.addEventListener('input', sync);

    const row = el('div', 'idea-labelrow');
    row.append(lab, count);
    wrap.append(row, input);
    form.appendChild(wrap);
    return { input, sync };
  };

  const nameF = field('idea-name', cfg.nameLabel || 'Title', NAME_MAX,
                      { placeholder: cfg.namePlaceholder || '' });
  const bodyF = field('idea-body', cfg.bodyLabel || 'Prompt', BODY_MAX,
                      { multiline: true, placeholder: cfg.bodyPlaceholder || '', rows: 4 });
  const contactF = field('idea-contact', cfg.contactLabel || 'Contact (optional)', CONTACT_MAX,
                         { placeholder: cfg.contactPlaceholder || '' });
  if (cfg.contactNote) {
    const note = el('p', 'idea-fine', cfg.contactNote);
    contactF.input.parentNode.appendChild(note);
    contactF.input.setAttribute('aria-describedby', 'idea-contact-note');
    note.id = 'idea-contact-note';
  }

  // honeypot: real people never see or fill this
  const hp = el('div', 'idea-hp');
  hp.setAttribute('aria-hidden', 'true');
  const hpInput = el('input');
  hpInput.type = 'text';
  hpInput.name = 'website';
  hpInput.tabIndex = -1;
  hpInput.autocomplete = 'off';
  const hpLabel = el('label', null, 'Website');
  hpLabel.appendChild(hpInput);
  hp.appendChild(hpLabel);
  form.appendChild(hp);

  const actions = el('div', 'idea-actions');
  const cancel = el('button', 'idea-cancel', 'Cancel');
  cancel.type = 'button';
  const submit = el('button', 'idea-submit', 'Send');
  submit.type = 'submit';
  actions.append(cancel, submit);
  form.appendChild(actions);

  const status = el('p', 'idea-status');
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  status.hidden = true;
  form.appendChild(status);

  dlg.appendChild(form);
  document.body.appendChild(dlg);

  // ---- behaviour
  const setStatus = (msg, kind) => {
    status.textContent = msg || '';
    status.hidden = !msg;
    status.className = 'idea-status' + (kind ? ' is-' + kind : '');
  };

  const reset = () => {
    setStatus('');
    submit.disabled = false;
    submit.textContent = 'Send';
    form.classList.remove('is-done');
  };

  const clear = () => {
    nameF.input.value = '';
    bodyF.input.value = '';
    contactF.input.value = '';
    nameF.sync(); bodyF.sync(); contactF.sync();
  };

  for (const btn of document.querySelectorAll('.idea-open')) {
    btn.addEventListener('click', () => {
      reset();
      dlg.showModal();
      nameF.input.focus();
    });
  }
  close.addEventListener('click', () => dlg.close());
  cancel.addEventListener('click', () => dlg.close());
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    if (hpInput.value.trim()) {                          // honeypot tripped
      form.classList.add('is-done');                     // look successful, send nothing
      setStatus(cfg.thanks || 'Got it — thank you.', 'ok');
      return;
    }

    const name = nameF.input.value.trim();
    const body = bodyF.input.value.trim();
    const contact = contactF.input.value.trim();

    if (!name) {
      setStatus('A short title, please — it makes these readable in a list.', 'err');
      nameF.input.focus();
      return;
    }
    if (body.length < BODY_MIN) {
      setStatus(`The prompt needs at least ${BODY_MIN} characters.`, 'err');
      bodyF.input.focus();
      return;
    }
    // The server rejects these too; catching them here saves a round trip and
    // gives a reason instead of a generic failure.
    if (/\bhttps?:\/\//i.test(name + ' ' + body)) {
      setStatus('Please leave links out of the title and prompt.', 'err');
      bodyF.input.focus();
      return;
    }

    const key = hash(normalize(name) + '|' + normalize(body));
    if (alreadySent().includes(key)) {
      form.classList.add('is-done');
      setStatus("You've already sent that one — it's in the pile.", 'ok');
      return;
    }

    const payload = {
      v: 1,
      nonce,
      name,
      body,
      contact,                                           // may be ''
      set: cfg.set || '',
      page: location.pathname,
      ts: new Date().toISOString(),
    };

    submit.disabled = true;
    submit.textContent = 'Sending…';
    setStatus('');

    if (!endpoint) {                                     // dry run
      console.log('[prompt-idea] dry run, would POST:', payload);
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

      if (r.status === 429) {                            // quota, not a failure
        submit.disabled = false;
        submit.textContent = 'Send';
        setStatus("That's enough ideas for one day — try again tomorrow.", 'err');
        return;
      }
      if (!r.ok) {
        let reason = '';
        try { reason = (await r.json()).error || ''; } catch {}
        throw new Error(reason || 'HTTP ' + r.status);
      }

      markSent(key);
      clear();
      form.classList.add('is-done');
      setStatus(cfg.thanks || 'Got it — thank you.', 'ok');
    } catch (err) {
      submit.disabled = false;
      submit.textContent = 'Try again';
      setStatus("That didn't go through. Please try again in a moment.", 'err');
      console.warn('[prompt-idea]', err.message);
    }
  });
})();
