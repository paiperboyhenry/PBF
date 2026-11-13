/* Site-wide behaviour: header, mobile menu, reveal, cursor, page transitions, filters, lightbox. */
(function () {
  'use strict';
  var d = document.documentElement;
  var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var $ = function (s, c) { return (c || document).querySelector(s); };
  var $$ = function (s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); };

  /* header turns solid after scrolling */
  var header = $('#site-header');
  function onScroll() { if (header) header.classList.toggle('is-solid', window.scrollY > 24); }
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });

  /* mobile menu */
  var btn = $('#menu-btn'), menu = $('#mnav');
  function setMenu(open) {
    if (!btn || !menu) return;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    menu.classList.toggle('is-open', open);
    document.body.classList.toggle('menu-open', open);
    if (header) header.classList.toggle('is-solid', open || window.scrollY > 24);
    if (header) header.classList.toggle('menu-dark', open);
    $('span', btn).textContent = open ? 'Close' : 'Menu';
    $$('a, button', menu).forEach(function (el) { el.tabIndex = open ? 0 : -1; });
    menu.toggleAttribute('inert', !open);
  }
  if (btn && menu) {
    setMenu(false);
    btn.addEventListener('click', function () { setMenu(btn.getAttribute('aria-expanded') !== 'true'); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && menu.classList.contains('is-open')) { setMenu(false); btn.focus(); } });
    matchMedia('(min-width: 980px)').addEventListener('change', function (e) { if (e.matches) setMenu(false); });
  }

  /* scroll reveal */
  var rev = $$('.reveal');
  if (rev.length) {
    if ('IntersectionObserver' in window && !reduce) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add('is-in'); io.unobserve(en.target); } });
      }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
      rev.forEach(function (el, i) { el.style.setProperty('--d', (i % 3) * 0.08 + 's'); io.observe(el); });
    } else { rev.forEach(function (el) { el.classList.add('is-in'); }); }
  }

  /* custom cursor (desktop, fine pointer only) */
  var cur = $('.cursor');
  if (cur && matchMedia('(hover: hover) and (pointer: fine)').matches) {
    var x = -100, y = -100, tx = x, ty = y, raf = 0;
    d.classList.add('has-cursor');
    var tick = function () {
      x += (tx - x) * (reduce ? 1 : 0.22); y += (ty - y) * (reduce ? 1 : 0.22);
      cur.style.transform = 'translate3d(' + x + 'px,' + y + 'px,0)';
      raf = (Math.abs(tx - x) + Math.abs(ty - y) > 0.3) ? requestAnimationFrame(tick) : 0;
    };
    window.addEventListener('pointermove', function (e) {
      if (e.pointerType === 'touch') return;
      tx = e.clientX; ty = e.clientY; cur.classList.add('is-on');
      if (!raf) raf = requestAnimationFrame(tick);
      var t = e.target.closest && e.target.closest('a, button, label, summary, [data-cursor], .door');
      cur.classList.toggle('is-link', !!t);
    }, { passive: true });
    document.addEventListener('pointerleave', function () { cur.classList.remove('is-on'); });
    window.addEventListener('pointerdown', function () { cur.classList.add('is-down'); });
    window.addEventListener('pointerup', function () { cur.classList.remove('is-down'); });
  }

  /* page transitions: a quick curtain between internal pages */
  if (d.classList.contains('is-arriving')) {
    requestAnimationFrame(function () { requestAnimationFrame(function () {
      d.classList.add('arrive-go');
      setTimeout(function () { d.classList.remove('is-arriving', 'arrive-go'); }, 650);
    }); });
  }
  window.addEventListener('pageshow', function (e) { if (e.persisted) d.classList.remove('is-leaving'); });
  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest('a[href]');
    if (!a || a.target === '_blank' || a.hasAttribute('download') || a.hasAttribute('data-no-transition')) return;
    var u; try { u = new URL(a.href, location.href); } catch (err) { return; }
    if (u.origin !== location.origin || u.pathname.indexOf('/admin') === 0 || u.pathname.indexOf('/media/') === 0) return;
    if (u.pathname === location.pathname && u.search === location.search) return; // same page / hash jump
    if (reduce || d.getAttribute('data-page') === 'warehouse' && a.closest('.door, .bay')) return;
    if (u.pathname === '/' && a.hasAttribute('data-reception')) { try { sessionStorage.removeItem('pbf_intro_s'); } catch (err) {} }
    e.preventDefault();
    try { sessionStorage.setItem('pbf_nav', '1'); } catch (err) {}
    d.classList.add('is-leaving');
    setTimeout(function () { location.href = a.href; }, 420);
  });

  /* category / department filters */
  $$('[data-filters]').forEach(function (group) {
    var grid = $('[data-filterable]');
    if (!grid) return;
    var byDept = !!grid.getAttribute('data-filter-attr');
    group.addEventListener('click', function (e) {
      var b = e.target.closest('[data-filter]');
      if (!b) return;
      $$('[data-filter]', group).forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
      var val = b.getAttribute('data-filter');
      $$(byDept ? '.pcard-wrap' : '.pcard', grid).forEach(function (el) {
        var v = byDept ? el.getAttribute('data-dept') : el.getAttribute('data-category');
        el.hidden = !!val && v !== val;
      });
    });
  });

  /* lightbox for gallery images */
  var boxes = $$('[data-lightbox]');
  if (boxes.length) {
    var lb = document.createElement('div');
    lb.className = 'lightbox'; lb.setAttribute('role', 'dialog'); lb.setAttribute('aria-modal', 'true'); lb.setAttribute('aria-label', 'Image viewer');
    lb.innerHTML = '<span class="lb-count"></span><button class="lb-close" type="button" aria-label="Close">✕</button><button class="lb-prev" type="button" aria-label="Previous image">←</button><button class="lb-next" type="button" aria-label="Next image">→</button><img alt="">';
    document.body.appendChild(lb);
    var items = [], idx = 0, opener = null;
    var img = $('img', lb), count = $('.lb-count', lb);
    var show = function (i) {
      idx = (i + items.length) % items.length;
      var src = items[idx].getAttribute('data-full');
      img.src = src; img.alt = ($('img', items[idx]) || {}).alt || '';
      count.textContent = (idx + 1) + ' / ' + items.length;
    };
    var close = function () { lb.classList.remove('is-open'); document.body.style.overflow = ''; if (opener) opener.focus(); };
    boxes.forEach(function (box) {
      var figs = $$('.fig', box);
      figs.forEach(function (f) {
        f.tabIndex = 0; f.setAttribute('role', 'button'); f.setAttribute('aria-label', 'Open image full screen');
        var open = function () { items = figs; opener = f; lb.classList.add('is-open'); document.body.style.overflow = 'hidden'; show(figs.indexOf(f)); $('.lb-close', lb).focus(); };
        f.addEventListener('click', open);
        f.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
      });
    });
    lb.addEventListener('click', function (e) {
      if (e.target.closest('.lb-close') || e.target === lb) close();
      else if (e.target.closest('.lb-prev')) show(idx - 1);
      else if (e.target.closest('.lb-next')) show(idx + 1);
    });
    document.addEventListener('keydown', function (e) {
      if (!lb.classList.contains('is-open')) return;
      if (e.key === 'Escape') close(); else if (e.key === 'ArrowLeft') show(idx - 1); else if (e.key === 'ArrowRight') show(idx + 1);
    });
  }
})();
