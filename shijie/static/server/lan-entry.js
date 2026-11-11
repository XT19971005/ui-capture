/* An entry fragment is not sent in HTTP requests or saved in server logs. */
'use strict';
(() => {
  const form = document.querySelector('form[data-lan-entry]');
  if (!form) return;
  const params = new URLSearchParams(location.hash.slice(1));
  const code = params.get('access');
  if (location.hash) history.replaceState(null, '', location.pathname + location.search);
  if (form.dataset.admitted === 'true') {
    location.replace(form.elements.next.value || '/image-editor.html');
    return;
  }
  if (code && code.length >= 8 && code.length <= 80 && !/[\r\n\0]/.test(code)) {
    form.elements.access_code.value = code;
    if (typeof form.requestSubmit === 'function') form.requestSubmit();
    else form.querySelector('button[type="submit"]').click();
  }
})();
