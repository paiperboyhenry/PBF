/* The open-plan warehouse: sideways exploration, department rail, door-opening transition. */
(function () {
  'use strict';
  var hall = document.getElementById('hall');
  var scroller = document.getElementById('hall-scroll');
  if (!hall || !scroller) return;
  var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var wide = matchMedia('(min-width: 900px)');
  var bays = Array.prototype.slice.call(hall.querySelectorAll('.bay'));
  var railBtns = Array.prototype.slice.call(hall.querySelectorAll('[data-goto]'));
  var current = 0;

  function centreOf(i) { var b = bays[i]; return b.offsetLeft + b.offsetWidth / 2 - scroller.clientWidth / 2; }
  function goTo(i) {
    i = Math.max(0, Math.min(bays.length - 1, i));
    if (wide.matches) scroller.scrollTo({ left: centreOf(i), behavior: reduce ? 'auto' : 'smooth' });
    else bays[i].scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
    setCurrent(i);
  }
  function setCurrent(i) {
    current = i;
    railBtns.forEach(function (b, k) { if (k === i) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current'); });
    var rail = hall.querySelector('.hall__rail ol'); var active = railBtns[i];
    if (rail && active && wide.matches) { var li = active.parentNode; rail.scrollLeft = li.offsetLeft - rail.clientWidth / 2 + li.offsetWidth / 2; }
  }
  function nearest() {
    var mid = scroller.scrollLeft + scroller.clientWidth / 2, best = 0, bd = Infinity;
    bays.forEach(function (b, i) { var dd = Math.abs(b.offsetLeft + b.offsetWidth / 2 - mid); if (dd < bd) { bd = dd; best = i; } });
    return best;
  }
  scroller.addEventListener('scroll', function () { if (wide.matches) setCurrent(nearest()); }, { passive: true });
  hall.addEventListener('click', function (e) {
    var g = e.target.closest('[data-goto]'); if (g) { goTo(+g.getAttribute('data-goto')); return; }
    var dir = e.target.closest('[data-dir]'); if (dir) goTo(current + (+dir.getAttribute('data-dir')));
  });

  /* wheel: vertical scroll moves sideways while the pointer is over the hall (desktop only) */
  scroller.addEventListener('wheel', function (e) {
    if (!wide.matches || Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
    var max = scroller.scrollWidth - scroller.clientWidth;
    var atEnd = (e.deltaY > 0 && scroller.scrollLeft >= max - 2) || (e.deltaY < 0 && scroller.scrollLeft <= 2);
    if (atEnd) return; // let the page scroll to the footer
    e.preventDefault();
    scroller.scrollLeft += e.deltaY;
  }, { passive: false });

  /* drag to pan with a mouse */
  var down = false, sx = 0, sl = 0, moved = 0;
  scroller.addEventListener('pointerdown', function (e) {
    if (e.pointerType !== 'mouse' || e.button !== 0 || !wide.matches) return;
    down = true; moved = 0; sx = e.clientX; sl = scroller.scrollLeft;
  });
  window.addEventListener('pointermove', function (e) {
    if (!down) return;
    var dx = e.clientX - sx; moved = Math.max(moved, Math.abs(dx));
    if (moved > 6) { hall.classList.add('is-dragging'); scroller.scrollLeft = sl - dx; }
  });
  window.addEventListener('pointerup', function () { down = false; setTimeout(function () { hall.classList.remove('is-dragging'); }, 0); });
  scroller.addEventListener('click', function (e) { if (moved > 6) { e.preventDefault(); e.stopPropagation(); moved = 0; } }, true);

  /* keyboard: arrows move between departments when focus is inside the hall */
  hall.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowRight') { goTo(current + 1); e.preventDefault(); }
    else if (e.key === 'ArrowLeft') { goTo(current - 1); e.preventDefault(); }
  });
  hall.addEventListener('focusin', function (e) {
    var bay = e.target.closest && e.target.closest('.bay');
    if (bay && wide.matches) { var i = bays.indexOf(bay); if (i !== current) goTo(i); }
  });

  /* entering a department: the door swings open and the camera pushes in */
  hall.addEventListener('click', function (e) {
    var a = e.target.closest('.door, .bay__enter'); if (!a) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;
    var bay = a.closest('.bay');
    var href = (bay.querySelector('.door') || a).href;
    if (reduce) return; // plain navigation
    e.preventDefault();
    if (hall.classList.contains('is-entering')) return;
    bay.classList.add('is-open');
    if (wide.matches) {
      var r = bay.getBoundingClientRect();
      hall.style.setProperty('--ox', ((r.left + r.width / 2 + scroller.scrollLeft) / scroller.scrollWidth * 100) + '%');
      setTimeout(function () { hall.classList.add('is-entering'); }, 550);
      setTimeout(function () { location.href = href; }, 1350);
    } else { setTimeout(function () { location.href = href; }, 800); }
  });

  /* arriving with #departments or from the picker: start at the first door */
  setCurrent(0);
  var hint = document.getElementById('hall-hint');
  if (hint) setTimeout(function () { hint.style.transition = 'opacity 1s'; hint.style.opacity = '0'; }, 7000);
  window.addEventListener('pageshow', function (e) { if (e.persisted) { hall.classList.remove('is-entering'); bays.forEach(function (b) { b.classList.remove('is-open'); }); } });
})();
