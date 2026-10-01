// Deterministic timeline for marketing videos: the renderer calls window.render(t) per frame.
// Markup is declarative:
//   .scene[data-start][data-end]          visible between start and end (seconds), with fades
//   [data-in="s"] [data-anim=rise|pop|left|right|fade] [data-out="s"]   relative to the scene start
//   [data-count="from,to,start,dur"] [data-prefix] [data-suffix] [data-decimals]   animated numbers
//   [data-at="s:class s:class"]           add classes from a time on (relative to scene)
(function () {
  const ease = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : 1 - Math.pow(1 - x, 3));
  const clamp = (x) => Math.max(0, Math.min(1, x));
  window.DURATION = 0;
  document.querySelectorAll(".scene").forEach((s) => (window.DURATION = Math.max(window.DURATION, +s.dataset.end)));

  window.render = function (t) {
    document.querySelectorAll(".scene").forEach((scene) => {
      const a = +scene.dataset.start, b = +scene.dataset.end;
      const fadeIn = a === 0 ? 1 : clamp((t - a) / 0.45);
      const fadeOut = b >= window.DURATION ? 1 : clamp((b - t) / 0.45);
      const vis = t >= a - 0.01 && t <= b + 0.01;
      scene.style.display = vis ? "block" : "none";
      scene.style.opacity = Math.min(fadeIn, fadeOut);
      if (!vis) return;
      const rt = t - a;
      scene.querySelectorAll("[data-in]").forEach((el) => {
        const p = ease((rt - +el.dataset.in) / (+el.dataset.dur || 0.6));
        const out = el.dataset.out ? 1 - ease((rt - +el.dataset.out) / 0.4) : 1;
        const kind = el.dataset.anim || "rise";
        const tf = { rise: `translateY(${(1 - p) * 40}px)`, pop: `scale(${0.85 + 0.15 * p})`,
          left: `translateX(${(1 - p) * -80}px)`, right: `translateX(${(1 - p) * 80}px)`, fade: "none" }[kind];
        el.style.opacity = p * out;
        el.style.transform = tf;
      });
      scene.querySelectorAll("[data-count]").forEach((el) => {
        const [from, to, start, dur] = el.dataset.count.split(",").map(Number);
        const v = from + (to - from) * ease((rt - start) / dur);
        const d = +(el.dataset.decimals || 0);
        el.textContent = (el.dataset.prefix || "") + v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }) + (el.dataset.suffix || "");
      });
      scene.querySelectorAll("[data-at]").forEach((el) => {
        el.dataset.at.split(" ").forEach((pair) => {
          const [when, cls] = pair.split(":");
          el.classList.toggle(cls, rt >= +when);
        });
      });
    });
  };
  window.render(+(new URLSearchParams(location.search).get("t") || 0));
})();
