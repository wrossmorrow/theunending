// "Show more": reveal a list's children in batches.
//
//   <ol data-batch="12" data-batch-narrow="6" id="...">…</ol>
//
// data-batch-narrow applies at phone widths (≤560px). Without JS every item
// shows. How far the visitor got is kept in history.state, keyed by the
// list's id, so Back from an item lands where they were.
(() => {
  const narrow = matchMedia('(max-width: 560px)').matches;

  document.querySelectorAll('[data-batch]').forEach((list, n) => {
    const step = Number((narrow && list.dataset.batchNarrow) || list.dataset.batch) || 12;
    const items = [...list.children];
    if (items.length <= step) return;

    const key = `shown:${list.id || n}`;
    let shown = Math.max(step, Number(history.state?.[key]) || 0);

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'show-more';
    list.after(btn);

    const render = () => {
      items.forEach((el, i) => { el.hidden = i >= shown; });
      const left = items.length - shown;
      if (left <= 0) btn.remove();
      else btn.textContent = `Show more (${left} left)`;
    };

    btn.addEventListener('click', () => {
      const firstNew = items[shown];
      shown += step;
      history.replaceState({ ...history.state, [key]: shown }, '');
      render();
      // move focus into the new batch without jumping the page
      firstNew?.querySelector('a:not([tabindex="-1"])')?.focus({ preventScroll: true });
    });

    render();
  });
})();
