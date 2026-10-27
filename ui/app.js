// Dialog behaviour Gradio does not provide: dialog semantics, focus on the safe choice when one opens, Esc to
// cancel the live-run confirm. The approval dialog has no Esc: closing it must be an answer, never an accident.
(() => {
  const DIALOGS = [
    { id: "confirm-modal", title: "confirm-title", focus: "confirm-cancel", escape: "confirm-cancel" },
    { id: "approval-modal", title: "approval-title", focus: "approval-later", escape: null },
  ];
  const open = {};
  const isShown = (el) => !!el && el.getClientRects().length > 0;

  function sync() {
    for (const d of DIALOGS) {
      const el = document.getElementById(d.id);
      if (!el) continue;
      if (el.getAttribute("role") !== "dialog") {
        el.setAttribute("role", "dialog");
        el.setAttribute("aria-modal", "true");
        el.setAttribute("aria-labelledby", d.title);
      }
      const shown = isShown(el);
      if (shown && !open[d.id]) document.getElementById(d.focus)?.focus();
      open[d.id] = shown;
    }
  }

  new MutationObserver(sync).observe(document.documentElement, {
    subtree: true, childList: true, attributes: true, attributeFilter: ["class", "style"],
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    for (const d of DIALOGS) {
      if (d.escape && isShown(document.getElementById(d.id))) document.getElementById(d.escape)?.click();
    }
  });
})();
