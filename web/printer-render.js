/* Keep the decoded preview node across progress/status updates. */
(() => {
  function replace(card, html) {
    const previous = card.querySelector('.printer-preview img');
    if (!previous) {card.innerHTML = html; return;}
    const template = document.createElement('template');
    template.innerHTML = html;
    const next = template.content.querySelector('.printer-preview img');
    const placeholder = template.content.querySelector('.printer-preview .printer-mark');
    if (next) {
      const url = next.getAttribute('src');
      next.replaceWith(previous);
      const pending = card._previewNext === url;
      card._previewNext = url;
      if (url !== previous.getAttribute('src') && !pending) {
        const preload = new Image();
        preload.onload = () => {
          if (card._previewNext === url && previous.isConnected) previous.setAttribute('src', url);
        };
        // Leave the decoded old image visible on failure; retry only for a new version.
        preload.onerror = () => {};
        preload.src = url;
      }
    } else if (placeholder) placeholder.replaceWith(previous);
    card.replaceChildren(template.content);
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {replace};
  else window.DeskMonPrinterRender = {replace};
})();
