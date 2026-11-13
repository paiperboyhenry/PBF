/* Runs before first paint: decides whether the cinematic intro plays, so there is no flash. */
(function () {
  var d = document.documentElement;
  d.classList.remove('no-js');
  d.classList.add('js');
  var reduce = false, small = false;
  try {
    reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    small = matchMedia('(max-width: 760px)').matches;
  } catch (e) {}
  if (small) d.classList.add('is-small');
  var mode = 'none';
  if (d.getAttribute('data-page') === 'home' && !reduce) {
    var session = null, pref = null;
    try { session = sessionStorage.getItem('pbf_intro_s'); pref = localStorage.getItem('pbf_intro'); } catch (e) {}
    if (location.hash === '#replay') mode = 'full';
    else if (session) mode = 'none';       // already entered during this visit
    else if (pref === 'skip') mode = 'none'; // visitor chose to skip before
    else if (pref === 'seen') mode = 'short'; // returning visitor: quick entrance
    else mode = 'full';
  }
  d.classList.add('intro-' + mode);
  if (mode === 'none') d.classList.add('rc-live');
  // Page-to-page curtain: only when we arrived via an internal link.
  try {
    if (sessionStorage.getItem('pbf_nav') === '1' && !reduce && d.getAttribute('data-page') !== 'home') {
      sessionStorage.removeItem('pbf_nav');
      d.classList.add('is-arriving');
    } else { sessionStorage.removeItem('pbf_nav'); }
  } catch (e) {}
})();
