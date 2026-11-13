/* Home: cinematic entrance sequence, reception actions and the department picker. */
(function () {
  'use strict';
  var d = document.documentElement;
  var intro = document.getElementById('intro');
  var stage = document.getElementById('stage');
  var reception = document.getElementById('reception');
  var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var mode = d.classList.contains('intro-full') ? 'full' : d.classList.contains('intro-short') ? 'short' : 'none';
  var small = d.classList.contains('is-small');
  var timers = [];
  var finished = false;

  function later(fn, ms) { timers.push(setTimeout(fn, ms)); }
  function remember(value) { try { localStorage.setItem('pbf_intro', value); sessionStorage.setItem('pbf_intro_s', '1'); } catch (e) {} }

  function finish(skipped) {
    if (finished) return;
    finished = true;
    timers.forEach(clearTimeout);
    if (intro) {
      intro.classList.add('is-done');
      later(function () { intro.hidden = true; intro.style.display = 'none'; }, 1000);
    }
    d.classList.add('rc-live');
    if (skipped) remember('skip'); else remember('seen');
    var h1 = document.getElementById('welcome-title');
    if (h1) { h1.setAttribute('tabindex', '-1'); }
  }

  function playIntro() {
    var load = document.getElementById('intro-load');
    var ready = Promise.all([
      document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve(),
      new Promise(function (res) { if (document.readyState === 'complete') res(); else window.addEventListener('load', res, { once: true }); })
    ]);
    if (load) load.style.setProperty('--p', '0.35');
    var minBrand = mode === 'short' ? 700 : 1500;
    var t0 = performance.now();
    Promise.race([ready, new Promise(function (r) { setTimeout(r, 4000); })]).then(function () {
      if (load) load.style.setProperty('--p', '1');
      var wait = Math.max(0, minBrand - (performance.now() - t0));
      later(function () { sequence(); }, wait);
    });
  }

  function sequence() {
    if (finished) return;
    if (mode === 'short') {
      // returning visitor: brand flash, then straight through the doors
      intro.classList.add('is-open');
      stage.classList.add('is-dolly-short');
      later(function () { finish(false); }, small ? 1100 : 1300);
      return;
    }
    if (small) {
      // mobile: simplified split-door reveal, no heavy scene
      intro.classList.add('is-ext');
      later(function () { intro.classList.add('is-open'); stage.classList.add('is-dolly-short'); }, 500);
      later(function () { finish(false); }, 2100);
      return;
    }
    // desktop: exterior -> push towards entrance -> doors open -> into reception
    intro.classList.add('is-ext');
    later(function () { intro.classList.add('is-push'); }, 250);
    later(function () { intro.classList.add('is-open'); }, 3300);
    later(function () { stage.classList.add('is-dolly'); }, 4300);
    later(function () { finish(false); }, 5300);
  }

  if (mode !== 'none' && intro && !reduce) {
    document.getElementById('intro-skip').addEventListener('click', function () { finish(true); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !finished && mode !== 'none') finish(true); });
    playIntro();
    // fail-safe: never trap a visitor behind the intro
    setTimeout(function () { finish(false); }, 9000);
  } else {
    if (intro) intro.style.display = 'none';
    d.classList.add('rc-live');
    if (mode !== 'none') remember('seen');
    else { try { sessionStorage.setItem('pbf_intro_s', '1'); } catch (e) {} }
  }

  /* replay */
  var replay = document.getElementById('replay');
  if (replay) replay.addEventListener('click', function () {
    try { sessionStorage.removeItem('pbf_intro_s'); localStorage.removeItem('pbf_intro'); } catch (e) {}
    if (location.hash === '#replay') location.reload(); else location.hash = 'replay', location.reload();
  });

  /* option 01: walk into the warehouse */
  var go = document.getElementById('opt-warehouse');
  if (go) go.addEventListener('click', function (e) {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;
    if (reduce) return;
    e.preventDefault();
    reception.classList.add('rc-leave');
    setTimeout(function () { location.href = go.href; }, 1000);
  });

  /* option 02: department picker */
  var pick = document.getElementById('opt-picker');
  var panel = document.getElementById('picker');
  var closeBtn = document.getElementById('picker-close');
  var returnFocus = null;
  function openPicker() {
    returnFocus = document.activeElement; panel.hidden = false; document.body.style.overflow = 'hidden';
    var first = panel.querySelector('a'); if (first) first.focus();
  }
  function closePicker() { panel.hidden = true; document.body.style.overflow = ''; if (returnFocus) returnFocus.focus(); }
  if (pick && panel) {
    pick.addEventListener('click', function (e) { if (e.metaKey || e.ctrlKey || e.shiftKey || e.button) return; e.preventDefault(); openPicker(); });
    closeBtn.addEventListener('click', closePicker);
    document.addEventListener('keydown', function (e) {
      if (panel.hidden) return;
      if (e.key === 'Escape') { closePicker(); return; }
      if (e.key === 'Tab') { // keep focus inside the dialog
        var f = panel.querySelectorAll('a, button'); var first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    });
  }
})();
