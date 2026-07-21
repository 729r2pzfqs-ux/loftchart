/* LoftChart client-side model search */
(function () {
  "use strict";

  var input = document.getElementById("lc-search");
  var box = document.getElementById("lc-results");
  if (!input || !box) return;

  var base = input.getAttribute("data-base") || "";
  var models = null;
  var loading = false;
  var active = -1;
  var current = [];

  function load(cb) {
    if (models) { cb(); return; }
    if (loading) return;
    loading = true;
    fetch(base + "search-index.json")
      .then(function (r) { return r.json(); })
      .then(function (d) { models = d; loading = false; cb(); })
      .catch(function () { loading = false; });
  }

  function score(m, q) {
    var hay = m.t.toLowerCase();
    var i = hay.indexOf(q);
    if (i === 0) return 0;
    if (i > 0) return 1;
    // fall back to matching all query words in any order
    var words = q.split(/\s+/).filter(Boolean);
    for (var w = 0; w < words.length; w++) {
      if (hay.indexOf(words[w]) === -1) return -1;
    }
    return 2;
  }

  function render(list, q) {
    current = list;
    active = -1;
    if (!q) { box.innerHTML = ""; return; }
    if (!list.length) {
      box.innerHTML = '<div class="sr-none">No models match &ldquo;' +
        q.replace(/[&<>"]/g, "") + '&rdquo;.</div>';
      return;
    }
    box.innerHTML = list.map(function (m) {
      return '<a href="' + base + m.u + '"><strong>' + m.t + '</strong>' +
        '<span class="sr-meta">' + m.m + '</span></a>';
    }).join("");
  }

  function search() {
    var q = input.value.trim().toLowerCase();
    if (!q) { render([], q); return; }
    load(function () {
      if (!models) return;
      var hits = [];
      for (var i = 0; i < models.length; i++) {
        var s = score(models[i], q);
        if (s >= 0) hits.push([s, i, models[i]]);
      }
      hits.sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
      render(hits.slice(0, 12).map(function (h) { return h[2]; }), q);
    });
  }

  function move(delta) {
    var links = box.querySelectorAll("a");
    if (!links.length) return;
    if (active >= 0) links[active].classList.remove("active");
    active = (active + delta + links.length) % links.length;
    links[active].classList.add("active");
    links[active].scrollIntoView({ block: "nearest" });
  }

  input.addEventListener("input", search);
  input.addEventListener("focus", function () { load(function () {}); });

  input.addEventListener("keydown", function (e) {
    if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Enter") {
      var links = box.querySelectorAll("a");
      if (active >= 0 && links[active]) { e.preventDefault(); window.location.href = links[active].href; }
      else if (links.length === 1) { e.preventDefault(); window.location.href = links[0].href; }
    } else if (e.key === "Escape") { input.value = ""; render([], ""); input.blur(); }
  });

  document.addEventListener("click", function (e) {
    if (!box.contains(e.target) && e.target !== input) box.innerHTML = "";
  });

  /* club-type filter chips on brand pages */
  var chips = document.querySelectorAll("[data-filter]");
  if (chips.length) {
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        var f = chip.getAttribute("data-filter");
        chips.forEach(function (c) { c.setAttribute("aria-pressed", c === chip ? "true" : "false"); });
        document.querySelectorAll("[data-club-type]").forEach(function (row) {
          var show = f === "all" || row.getAttribute("data-club-type") === f;
          row.style.display = show ? "" : "none";
        });
        document.querySelectorAll("[data-decade-group]").forEach(function (g) {
          var visible = g.querySelectorAll('[data-club-type]:not([style*="display: none"])').length;
          g.style.display = visible ? "" : "none";
        });
      });
    });
  }
})();
