/* Admin helpers: dependent category list, auto-submitting filters. No third-party code. */
(function () {
  'use strict';
  var dept = document.getElementById('department_id');
  var cat = document.getElementById('category');
  if (dept && cat) {
    var map = {};
    try { map = JSON.parse(dept.getAttribute('data-cats') || '{}'); } catch (e) {}
    var current = cat.getAttribute('data-current') || '';
    var fill = function () {
      var list = map[dept.value] || [];
      var keep = cat.value || current;
      cat.innerHTML = '';
      var none = document.createElement('option'); none.value = ''; none.textContent = list.length ? 'None' : 'Choose a department first'; cat.appendChild(none);
      list.forEach(function (c) { var o = document.createElement('option'); o.value = c; o.textContent = c; if (c === keep) o.selected = true; cat.appendChild(o); });
      current = '';
    };
    dept.addEventListener('change', function () { cat.value = ''; fill(); });
    fill();
  }
  document.querySelectorAll('[data-autosubmit]').forEach(function (el) {
    el.addEventListener('change', function () { el.form && el.form.submit(); });
  });
})();
