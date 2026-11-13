/* Multi-step enquiry form. Without JavaScript every step is visible and the form posts normally. */
(function () {
  'use strict';
  var form = document.getElementById('enquiry-form');
  if (!form) return;
  var steps = Array.prototype.slice.call(form.querySelectorAll('.fstep'));
  var bars = Array.prototype.slice.call(document.querySelectorAll('#steps li'));
  var btnBack = document.getElementById('btn-back'), btnNext = document.getElementById('btn-next'), btnSend = document.getElementById('btn-send');
  var label = document.getElementById('step-label'), nameEl = document.getElementById('step-name');
  var topErr = document.getElementById('form-error');
  var other = document.getElementById('other-wrap');
  var maxFiles = +form.getAttribute('data-max-files') || 3, maxMb = +form.getAttribute('data-max-mb') || 8;
  var i = 0;
  var EMAIL = /^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$/;

  // Start on the first step with a server-side error, if any
  var firstErr = form.querySelector('.has-error, .err:not(:empty)');
  if (firstErr) { var st = firstErr.closest('.fstep'); if (st) i = steps.indexOf(st); }

  function setErr(name, msg) {
    var el = form.querySelector('[data-err="' + name + '"]');
    if (el) el.textContent = msg || '';
    var f = el && el.closest('.field') || (form.querySelector('[name="' + name + '"]') || {}).closest && form.querySelector('[name="' + name + '"]').closest('.field');
    if (f) f.classList.toggle('has-error', !!msg);
  }
  function showTop(msg) { topErr.hidden = !msg; topErr.textContent = msg || ''; if (msg) topErr.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
  function val(n) { var el = form.elements[n]; return el ? (el.value || '').trim() : ''; }

  function check(n) {
    var ok = true, first = null;
    function bad(name, msg) { setErr(name, msg); ok = false; if (!first) first = form.elements[name]; }
    if (n === 0) {
      setErr('full_name'); setErr('email'); setErr('whatsapp');
      if (!val('full_name')) bad('full_name', 'Please tell us your name.');
      if (!val('email')) bad('email', 'Please add an email address so we can reply.');
      else if (!EMAIL.test(val('email'))) bad('email', 'That email address doesn’t look right.');
      var wa = val('whatsapp').replace(/\D/g, '');
      if (val('whatsapp') && (wa.length < 7 || wa.length > 15)) bad('whatsapp', 'Enter your WhatsApp number with country code, e.g. +254…');
    } else if (n === 1) {
      setErr('services'); setErr('service_other');
      var picked = form.querySelectorAll('input[name="services"]:checked');
      if (!picked.length) bad('services', 'Choose at least one service.');
      var otherOn = Array.prototype.some.call(picked, function (c) { return c.value === 'Other'; });
      if (otherOn && !val('service_other')) bad('service_other', 'Tell us what else you need.');
    } else if (n === 2) {
      setErr('description');
      if (val('description').length < 20) bad('description', 'Tell us a little more about the project (a few sentences is plenty).');
    } else if (n === 5) {
      setErr('attachments');
      var files = form.elements['attachments'].files;
      if (files.length > maxFiles) bad('attachments', 'Attach up to ' + maxFiles + ' files.');
      for (var k = 0; k < files.length; k++) if (files[k].size > maxMb * 1024 * 1024) { bad('attachments', files[k].name + ' is larger than ' + maxMb + ' MB.'); break; }
    }
    if (first && first.focus) first.focus();
    return ok;
  }

  function review() {
    var list = document.getElementById('review-list'), wrap = document.getElementById('review');
    var rows = [
      ['Name', val('full_name')], ['Business', val('business_name')], ['Email', val('email')], ['WhatsApp', val('whatsapp')], ['Country', val('country')],
      ['Services', Array.prototype.map.call(form.querySelectorAll('input[name="services"]:checked'), function (c) { return c.value; }).join(', ') + (val('service_other') ? ' — ' + val('service_other') : '')],
      ['Project', val('description')], ['Budget', (form.querySelector('input[name="budget"]:checked') || {}).value || 'Not given'],
      ['Timeline', (form.querySelector('input[name="timeline"]:checked') || {}).value || 'Not given']
    ];
    list.innerHTML = '';
    rows.forEach(function (r) {
      if (!r[1]) return;
      var div = document.createElement('div'), dt = document.createElement('dt'), dd = document.createElement('dd');
      dt.textContent = r[0]; dd.textContent = r[1]; div.appendChild(dt); div.appendChild(dd); list.appendChild(div);
    });
    wrap.hidden = false;
  }

  function show(n, focus) {
    i = n;
    steps.forEach(function (s, k) { s.classList.toggle('is-current', k === n); });
    bars.forEach(function (b, k) { b.classList.toggle('is-done', k < n); b.classList.toggle('is-now', k === n); });
    label.textContent = 'Step ' + (n + 1) + ' of ' + steps.length;
    nameEl.textContent = steps[n].getAttribute('data-name');
    btnBack.hidden = n === 0; btnNext.hidden = n === steps.length - 1; btnSend.hidden = n !== steps.length - 1;
    if (n === steps.length - 1) review();
    if (focus) {
      var t = steps[n].querySelector('legend'); if (t) { t.setAttribute('tabindex', '-1'); t.focus({ preventScroll: true }); }
      form.closest('.wrap').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
    }
  }

  btnNext.addEventListener('click', function () { showTop(''); if (check(i)) show(i + 1, true); });
  btnBack.addEventListener('click', function () { showTop(''); show(i - 1, true); });
  form.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT' && e.target.type !== 'submit' && i < steps.length - 1) { e.preventDefault(); btnNext.click(); }
  });
  form.addEventListener('change', function (e) {
    if (e.target.name === 'services' && other) {
      var on = !!form.querySelector('input[name="services"][value="Other"]:checked');
      other.hidden = !on;
    }
  });
  if (other) other.hidden = !form.querySelector('input[name="services"][value="Other"]:checked');

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    showTop('');
    for (var n = 0; n < steps.length; n++) { if (!check(n)) { show(n, true); return; } }
    btnSend.disabled = true; var old = btnSend.innerHTML; btnSend.textContent = 'Sending…';
    fetch(form.action, { method: 'POST', body: new FormData(form), headers: { 'X-Requested-With': 'fetch', 'X-CSRF-Token': form.elements['csrf_token'].value }, credentials: 'same-origin' })
      .then(function (r) { return r.json().catch(function () { return { ok: false, message: 'Unexpected response from the server.' }; }).then(function (j) { return { status: r.status, body: j }; }); })
      .then(function (res) {
        var j = res.body;
        if (res.status === 200 && j.ok) { success(j); return; }
        btnSend.disabled = false; btnSend.innerHTML = old;
        if (j.errors && Object.keys(j.errors).length) {
          var firstStep = steps.length;
          Object.keys(j.errors).forEach(function (k) {
            setErr(k, j.errors[k]);
            var el = form.elements[k] ? (form.elements[k].length ? form.elements[k][0] : form.elements[k]) : form.querySelector('[data-err="' + k + '"]');
            var st = el && el.closest('.fstep'); if (st) firstStep = Math.min(firstStep, steps.indexOf(st));
          });
          if (firstStep < steps.length) show(firstStep, true);
        }
        showTop(j.message || 'We couldn’t send your enquiry. Nothing was sent — please try again.');
        if (window.turnstile) try { window.turnstile.reset(); } catch (err) {}
      })
      .catch(function () {
        btnSend.disabled = false; btnSend.innerHTML = old;
        showTop('We couldn’t reach the server. Your enquiry has not been sent — please check your connection and try again.');
      });
  });

  function success(j) {
    document.getElementById('form-panel').hidden = true;
    var done = document.getElementById('done');
    document.getElementById('done-ref').textContent = 'Reference ' + j.ref;
    if (j.email_confirmation) document.getElementById('done-mail').hidden = false;
    if (j.whatsapp_url) { var wa = document.getElementById('done-wa'); wa.href = j.whatsapp_url; wa.hidden = false; }
    done.hidden = false; done.focus(); window.scrollTo({ top: 0 });
  }

  show(i, false);
})();
