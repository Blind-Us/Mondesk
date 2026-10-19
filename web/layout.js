/* One layout coordinate system. OS resolution is separate from browser CSS pixels. */
(function (root) {
  function settings(display = {}) {
    const n = (v, fallback, low, high) => Number.isFinite(+v) && +v >= low && +v <= high ? +v : fallback;
    const width = n(display.width, 960, 320, 7680);
    const height = n(display.height, 640, 240, 4320);
    return { width, height, fit: display.fit === 'auto' ? 'auto' : 'contain',
      textScale: n(display.text_scale, 1, .8, 1.4) };
  }
  function calculate(viewWidth, viewHeight, display = {}) {
    const d = settings(display), vw = Math.max(1, viewWidth), vh = Math.max(1, viewHeight);
    const aspect = d.fit === 'auto' ? Math.max(1.25, Math.min(2.4, vw / vh)) : d.width / d.height;
    const height = 640 / d.textScale, width = height * aspect;
    const scale = Math.min(vw / width, vh / height);
    return { width, height, scale, aspect, contentWidth: width * scale, contentHeight: height * scale };
  }
  function panelDisplays(displays) {
    return displays.filter(d => !d.error && !d.primary && d.current && d.modes?.some(m => m.w === 960 && m.h === 640));
  }
  root.DeskMonLayout = { settings, calculate, panelDisplays };
})(globalThis);
