// Printable: lightbox for poster pages, "show more" for the /printable/ index.
(() => {
  // ---- lightbox: click a poster thumb to see its preview ----
  const box = document.getElementById('lightbox');
  if (box) {
    const big = box.querySelector('img');
    document.querySelectorAll('.poster-grid a, .poster-wide a').forEach(a =>
      a.addEventListener('click', e => {
        if (e.metaKey || e.ctrlKey) return;          // keep cmd/ctrl-click = new tab
        e.preventDefault();
        big.src = a.href;
        big.alt = a.querySelector('img').alt;
        box.showModal();                             // Esc closes it for free
      }));
    box.addEventListener('click', () => box.close()); // click anywhere to close
  }

  // ---- index: reveal tiles in batches. Without JS every tile shows. ----
  document.querySelectorAll('.poster-index[data-batch]').forEach(grid => {
    const step = Number(grid.dataset.batch) || 24;
    const tiles = [...grid.querySelectorAll('.poster-tile')];
    if (tiles.length <= step) return;

    // Remember how far the visitor got, so Back from a set page lands where they were.
    let shown = Math.max(step, Number(history.state?.postersShown) || 0);

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'poster-more';
    grid.after(btn);

    const render = () => {
      tiles.forEach((t, i) => { t.hidden = i >= shown; });
      const left = tiles.length - shown;
      if (left <= 0) btn.remove();
      else btn.textContent = `Show more (${left} left)`;
    };

    btn.addEventListener('click', () => {
      const firstNew = tiles[shown];
      shown += step;
      history.replaceState({ ...history.state, postersShown: shown }, '');
      render();
      firstNew?.focus({ preventScroll: true });
    });

    render();
  });
})();
