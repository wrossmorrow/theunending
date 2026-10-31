// Printable: lightbox for the per-set poster pages.
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
})();
