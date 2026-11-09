/* QA shim for src/map3d until the template's 지도 · 3D · 표 hook lands (AGENTS.md §3-5):
   puts <div id="map3d"> over #map in the same rect (the 2D map stays laid out, invisible) and calls KH3D.show() / hide(). */
(() => {
  if (window.__m3d) return;
  let ro = null;
  const place = () => {
    const map = document.getElementById('map'), d = document.getElementById('map3d');
    if (!map || !d) return;
    d.style.cssText = `position:absolute;left:${map.offsetLeft}px;top:${map.offsetTop}px;width:${map.offsetWidth}px;height:${map.offsetHeight}px;z-index:5`;
  };
  window.__m3d = {
    on() {
      const map = document.getElementById('map');
      const stage = map.parentElement;
      if (getComputedStyle(stage).position === 'static') stage.style.position = 'relative';
      let d = document.getElementById('map3d');
      if (!d) { d = document.createElement('div'); d.id = 'map3d'; map.after(d); }
      d.hidden = false;
      map.style.visibility = 'hidden';
      place();
      if (!ro) { ro = new ResizeObserver(place); ro.observe(map); }
      return window.KH3D.show();
    },
    off() {
      const map = document.getElementById('map'), d = document.getElementById('map3d');
      window.KH3D.hide();
      if (d) d.hidden = true;
      map.style.visibility = '';
      if (ro) { ro.disconnect(); ro = null; }
    },
  };
})();
