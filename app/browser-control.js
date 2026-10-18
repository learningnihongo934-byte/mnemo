// Page-side scripts injected into the browser view so Mnemo can see and act on pages.

// Numbered list of everything clickable/typeable, like an accessibility snapshot.
const SNAPSHOT = `(() => {
  const sel = 'a[href], button, input:not([type=hidden]), textarea, select, summary, [role=button], [role=link], ' +
              '[role=tab], [role=menuitem], [role=checkbox], [role=searchbox], [contenteditable=""], [contenteditable=true]';
  document.querySelectorAll('[data-mnemo-ref]').forEach(e => e.removeAttribute('data-mnemo-ref'));
  const out = [];
  let ref = 1;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    if (r.width < 2 || r.height < 2 || st.visibility === 'hidden' || st.display === 'none') continue;
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    let role = el.getAttribute('role') ||
      (tag === 'a' ? 'link' : tag === 'button' || type === 'submit' || type === 'button' ? 'button' :
       tag === 'select' ? 'combobox' : tag === 'textarea' ? 'textbox' :
       tag === 'input' ? (type === 'checkbox' ? 'checkbox' : type === 'radio' ? 'radio' :
                          type === 'search' ? 'searchbox' : 'textbox') : tag);
    if (el.isContentEditable && role === tag) role = 'textbox';
    const name = (el.getAttribute('aria-label') || el.innerText || el.value || el.getAttribute('placeholder') ||
                  el.getAttribute('title') || el.getAttribute('alt') || el.getAttribute('name') || '')
                  .replace(/\\s+/g, ' ').trim().slice(0, 120);
    el.setAttribute('data-mnemo-ref', ref);
    out.push({ ref, role, name, password: type === 'password',
               inView: r.bottom > 0 && r.top < innerHeight, href: el.href || undefined });
    if (++ref > 250) break;
  }
  out.sort((a, b) => (b.inView - a.inView));
  return { url: location.href, title: document.title, elements: out };
})()`;

// Centre of an element (scrolled into view), for a real mouse click.
const locate = (ref) => `(() => {
  const el = document.querySelector('[data-mnemo-ref="${Number(ref)}"]');
  if (!el) return null;
  el.scrollIntoView({ block: 'center', inline: 'center' });
  const r = el.getBoundingClientRect();
  return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2),
           w: r.width, h: r.height, left: r.left, top: r.top, password: el.type === 'password' };
})()`;

// Visible "Mnemo is acting here" highlight, like an agent cursor.
const highlight = (box, label) => `(() => {
  const d = document.createElement('div');
  d.style.cssText = 'position:fixed;z-index:2147483647;pointer-events:none;border:2px solid #7c5cff;' +
    'border-radius:6px;box-shadow:0 0 0 4px rgba(124,92,255,.25);transition:opacity .4s;' +
    'left:${box.left - 3}px;top:${box.top - 3}px;width:${box.w + 6}px;height:${box.h + 6}px';
  const t = document.createElement('div');
  t.textContent = ${JSON.stringify(label)};
  t.style.cssText = 'position:absolute;top:-22px;left:-2px;background:#7c5cff;color:#fff;font:600 11px system-ui;' +
    'padding:3px 7px;border-radius:5px;white-space:nowrap';
  d.appendChild(t);
  document.documentElement.appendChild(d);
  setTimeout(() => { d.style.opacity = '0'; setTimeout(() => d.remove(), 450); }, 1100);
})()`;

const clearField = (ref) => `(() => {
  const el = document.querySelector('[data-mnemo-ref="${Number(ref)}"]');
  if (!el) return false;
  el.focus();
  if ('value' in el) { el.value = ''; el.dispatchEvent(new Event('input', { bubbles: true })); }
  return true;
})()`;

const READ = `(() => {
  const main = document.querySelector('article, main, [role=main], #content, #mw-content-text') || document.body;
  const clone = main.cloneNode(true);
  clone.querySelectorAll('script, style, noscript, nav, footer, header, aside, form, iframe, svg').forEach(e => e.remove());
  return { url: location.href, title: document.title, text: clone.innerText.replace(/\\n{3,}/g, '\\n\\n').trim() };
})()`;

module.exports = { SNAPSHOT, locate, highlight, clearField, READ };
