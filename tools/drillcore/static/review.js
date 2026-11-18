// The review page: each claim the notes make, beside the passage of the source it cites.
//
// Everything a note or a source holds is shown as text (textContent), never as markup, and nothing is loaded from
// anywhere but the server that served this page. Every request carries the token the page was given when it loaded.
"use strict";

(() => {
  const TOKEN = document.querySelector('meta[name="review-token"]').getAttribute("content");
  const STORE = "drillcore.review.";
  const $ = (selector) => document.querySelector(selector);

  // Verdicts, worst first, with the class that colours them and the word shown.
  const VERDICTS = [["FAIL", "fail", "Fails"], ["warning", "warn", "Warning"], ["not judged", "open", "Not judged"],
    ["waived", "waived", "Waived"], ["pass", "pass", "Passes"]];
  const VCLASS = Object.fromEntries(VERDICTS.map(([verdict, cls]) => [verdict, cls]));
  const VWORD = Object.fromEntries(VERDICTS.map(([verdict, , word]) => [verdict, word]));
  const CHECKS = { numbers: "Figure", quotations: "Quotation", arithmetic: "Working", citations: "Citation",
    sections: "Section", waivers: "Waiver" };
  // How much of a source is shown either side of a passage at first, and how much more each time a reader asks.
  const AROUND = 2500;
  const MORE = 12000;

  const S = {
    state: null,
    cur: -1,          // the claim shown, by its place in state.claims
    view: 0,          // which of its sources
    hit: 0,           // which place in that source
    note: "",         // the note shown
    browse: null,     // a source opened from the note, with no claim
    win: null,        // the stretch of the source shown: { key, start, end }
    texts: new Map(), // source id -> { text, pages, title }
    ticket: 0,
    form: null,       // "disagree" | "accept" | "edit" | "name"
    editLine: null,   // { note, line } being edited
    pending: null,    // what to do once a name is given
    showLabels: load("labels", true),
    filters: loadFilters(),
    byLine: new Map(),
    links: new Map(),
    busy: false,
  };

  // ---------------------------------------------------------------- small helpers

  function load(key, fallback) {
    try {
      const value = localStorage.getItem(STORE + key);
      return value === null ? fallback : JSON.parse(value);
    } catch {
      return fallback;
    }
  }

  function save(key, value) {
    try {
      localStorage.setItem(STORE + key, JSON.stringify(value));
    } catch {
      // Storage may be off; the page works without it.
    }
  }

  function loadFilters() {
    const saved = load("filters", null) || {};
    return { off: new Set(Array.isArray(saved.off) ? saved.off : []), open: Boolean(saved.open), group: saved.group || "note" };
  }

  function saveFilters() {
    save("filters", { off: [...S.filters.off], open: S.filters.open, group: S.filters.group });
  }

  // An element, its attributes and its children. Text is always a text node.
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [name, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (name === "class") node.className = value;
      else if (name === "text") node.textContent = value;
      else if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
      else node.setAttribute(name, value === true ? "" : String(value));
    }
    for (const child of children.flat(Infinity)) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  const words = (status) => String(status || "").replace(/_/g, " ");
  const claims = () => (S.state ? S.state.claims : []);
  const claim = () => claims()[S.cur] || null;
  const lineKey = (note, line) => `${note}\u0000${line}`;
  const by = () => load("by", "");
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const host = (url) => {
    try {
      return new URL(url).host || url;
    } catch {
      return url;
    }
  };
  const webAddress = (url) => /^https?:\/\//i.test(url);

  // Scroll a pane, and only that pane, so an element is in view: centred, or just inside for a list.
  function reveal(pane, node, nearest) {
    if (!pane || !node) return;
    const box = pane.getBoundingClientRect();
    const at = node.getBoundingClientRect();
    if (nearest) {
      if (at.top < box.top) pane.scrollTop -= box.top - at.top + 8;
      else if (at.bottom > box.bottom) pane.scrollTop += at.bottom - box.bottom + 8;
      return;
    }
    pane.scrollTop += (at.top - box.top) - (pane.clientHeight - at.height) / 2;
  }

  function keyFor(source, note) {
    // The key a note gives a source, as "S1", from the source's keys, "note S1".
    const keys = source.keys.filter((key) => key.startsWith(`${note} `)).map((key) => key.slice(note.length + 1));
    return keys[0] || (source.keys[0] || "").split(" ").pop() || "Source";
  }

  // ---------------------------------------------------------------- talking to the server

  async function api(path, body) {
    const options = { headers: { "X-Review-Token": TOKEN }, cache: "no-store" };
    if (body !== undefined) {
      options.method = "POST";
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    let response;
    try {
      response = await fetch(path, options);
    } catch {
      throw new Error("The review server isn't answering. Is the review command still running?");
    }
    let data = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }
    if (!response.ok) throw new Error((data && data.error) || `${response.status} ${response.statusText}`);
    return data;
  }

  function claimRef(c) {
    return { note: c.note, line: c.line, check: c.check, item: c.item };
  }

  async function act(path, body, done) {
    if (S.busy) return;
    S.busy = true;
    document.body.classList.add("busy");
    const keep = claim() ? { ...claimRef(claim()), index: S.cur } : null;
    try {
      const data = await api(path, body);
      setState(data, keep, path === "/api/recheck");
      if (done) done(data);
    } catch (problem) {
      toast(problem.message, { error: true });
    } finally {
      S.busy = false;
      document.body.classList.remove("busy");
    }
  }

  function getText(id) {
    if (!S.texts.has(id)) {
      S.texts.set(id, api(`/api/source?id=${encodeURIComponent(id)}`).catch((problem) => {
        S.texts.delete(id);
        throw problem;
      }));
    }
    return S.texts.get(id);
  }

  // ---------------------------------------------------------------- state

  function setState(data, keep, reread) {
    const first = S.state === null;
    S.state = data;
    if (reread) S.texts.clear();
    S.byLine = new Map();
    data.claims.forEach((c, index) => {
      const key = lineKey(c.note, c.line);
      if (!S.byLine.has(key)) S.byLine.set(key, []);
      S.byLine.get(key).push(index);
    });
    S.links = new Map();
    for (const link of data.links) {
      const key = lineKey(link.note, link.line);
      if (!S.links.has(key)) S.links.set(key, []);
      S.links.get(key).push(link);
    }
    let index = keep ? findClaim(keep) : -1;
    if (index < 0 && first) index = firstToReview();
    const found = claims()[index];
    const same = Boolean(keep && found && found.note === keep.note && found.line === keep.line && found.check === keep.check &&
      found.item === keep.item);
    choose(index, { keepPlace: same, scroll: !same });
  }

  function findClaim(keep) {
    const list = claims();
    const exact = list.findIndex((c) => c.note === keep.note && c.line === keep.line && c.check === keep.check && c.item === keep.item);
    if (exact >= 0) return exact;
    const sameCheck = list.findIndex((c) => c.note === keep.note && c.line === keep.line && c.check === keep.check);
    if (sameCheck >= 0) return sameCheck;
    const sameLine = list.findIndex((c) => c.note === keep.note && c.line === keep.line);
    if (sameLine >= 0) return sameLine;
    return list.length ? clamp(keep.index, 0, list.length - 1) : -1;
  }

  function firstToReview() {
    const order = visibleOrder();
    const open = order.find((index) => !claims()[index].mark || claims()[index].stale);
    return open !== undefined ? open : (order.length ? order[0] : (claims().length ? 0 : -1));
  }

  function choose(index, options = {}) {
    S.cur = index;
    S.browse = null;
    if (!options.keepPlace) {
      S.form = null;
      S.editLine = null;
      S.hit = 0;
      S.win = null;
      const c = claim();
      S.view = c ? Math.max(0, c.views.findIndex((view) => view.hits.length)) : 0;
    }
    const c = claim();
    if (c && c.note) S.note = c.note;
    if (!S.note && S.state && S.state.notes.length) S.note = S.state.notes[0].file;
    render({ scroll: options.scroll !== false });
  }

  function visible(c) {
    return !S.filters.off.has(c.verdict) && (!S.filters.open || !c.mark || Boolean(c.stale));
  }

  function visibleOrder() {
    return claims().map((_, index) => index).filter((index) => visible(claims()[index]));
  }

  function step(direction, openOnly) {
    const order = visibleOrder().filter((index) => !openOnly || !claims()[index].mark || claims()[index].stale);
    if (!order.length) return;
    let next;
    if (direction > 0) next = order.find((index) => index > S.cur);
    else next = [...order].reverse().find((index) => index < S.cur);
    if (next === undefined) next = direction > 0 ? order[0] : order[order.length - 1];
    choose(next);
  }

  // ---------------------------------------------------------------- drawing

  function render(options = {}) {
    if (!S.state) return;
    renderTop();
    renderQueue(options.scroll);
    renderDoc(options.scroll);
    renderSource(options.source !== undefined ? options.source : options.scroll);
    renderBar();
  }

  function browse(id) {
    S.browse = id;
    S.win = null;
    render({ scroll: false, source: true });
  }

  function renderTop() {
    const st = S.state;
    document.title = `${st.name} review · ${st.workspace.name}`;
    $("#app-name").textContent = `${st.name} review`;
    $("#ws-name").textContent = st.workspace.name;
    $("#ws-name").title = st.workspace.root;
    const list = claims();
    const marked = list.filter((c) => c.mark && !c.stale).length;
    const disagree = list.filter((c) => c.mark && c.mark.mark === "disagrees").length;
    const again = list.filter((c) => c.mark && c.stale).length;
    $("#progress-fill").style.width = list.length ? `${(100 * marked) / list.length}%` : "0";
    const parts = [`${marked} of ${list.length} marked`];
    if (disagree) parts.push(`${disagree} disagree${disagree === 1 ? "s" : ""}`);
    if (again) parts.push(`${again} to look at again`);
    $("#progress-text").textContent = parts.join(" · ");
    const banner = $("#banner");
    if (st.readOnly) {
      banner.hidden = false;
      banner.textContent = `This is the example workspace that ships with ${st.name}, so the page shows it and changes nothing: ` +
        `marks, edits and waivers are off. Make a workspace of your own with \`${st.slug} init\` to review your notes.`;
    } else {
      banner.hidden = true;
    }
  }

  function renderQueue(scroll) {
    const counts = {};
    for (const c of claims()) counts[c.verdict] = (counts[c.verdict] || 0) + 1;
    $("#chips").replaceChildren(...VERDICTS.map(([verdict, cls, word]) => el("button", {
      type: "button", class: `chip v-${cls}${S.filters.off.has(verdict) ? " off" : ""}`, "data-verdict": verdict,
      "aria-pressed": String(!S.filters.off.has(verdict)), title: `Show or hide claims that ${word.toLowerCase()}`,
    }, el("span", { class: `dot v-${cls}` }), word, el("span", { class: "n", text: counts[verdict] || 0 }))));
    $("#only-open").checked = S.filters.open;
    $("#group-by").value = S.filters.group;

    const order = visibleOrder();
    const groups = [];
    if (S.filters.group === "source") {
      for (const source of S.state.sources) {
        const members = order.filter((index) => claims()[index].views.some((view) => view.source === source.id));
        if (members.length) groups.push([`${source.keys.map((key) => key.split(" ").pop()).join(", ") || "Source"} · ${source.title || host(source.url)}`, members]);
      }
      const none = order.filter((index) => !claims()[index].views.length);
      if (none.length) groups.push(["No source to compare", none]);
    } else if (S.filters.group === "verdict") {
      for (const [verdict, , word] of VERDICTS) {
        const members = order.filter((index) => claims()[index].verdict === verdict);
        if (members.length) groups.push([word, members]);
      }
    } else {
      const notes = [...S.state.notes.map((note) => note.file), ""];
      for (const note of notes) {
        const members = order.filter((index) => claims()[index].note === note);
        if (members.length) groups.push([note || "The workspace", members]);
      }
    }
    const list = $("#queue-list");
    if (!groups.length) {
      list.replaceChildren(el("p", { class: "empty", text: claims().length ? "No claim matches what's shown. Turn a verdict back on above." :
        "Nothing to review: the checks judged no claim. Fetch the sources the notes cite, then recheck." }));
      return;
    }
    list.replaceChildren(...groups.map(([title, members]) => el("section", { class: "group" },
      el("h3", {}, el("span", { text: title }), el("span", { text: members.length })),
      el("ol", {}, members.map((index) => el("li", {}, queueItem(index)))))));
    if (scroll) reveal(list, list.querySelector(".qitem.cur"), true);
  }

  function queueItem(index) {
    const c = claims()[index];
    let markIcon = null;
    if (c.mark) {
      const cls = c.stale ? "stale" : c.mark.mark;
      const symbol = c.stale ? "?" : (c.mark.mark === "agrees" ? "✓" : "✗");
      markIcon = el("span", { class: `qmark ${cls}`, title: c.stale ? `Marked, but ${c.stale}` : `Marked: ${c.mark.mark}`, text: symbol });
    }
    const where = c.line ? `line ${c.line}` : "the note";
    return el("button", { type: "button", class: `qitem${index === S.cur ? " cur" : ""}`, "data-claim": index,
      title: `${CHECKS[c.check] || c.check}: ${VWORD[c.verdict]} (${words(c.status)})` },
      el("span", { class: `dot v-${VCLASS[c.verdict]}` }),
      el("span", { class: "qtext", text: c.item || words(c.status) }),
      el("span", { class: "qmeta", text: `${CHECKS[c.check] || c.check} · ${where} · ${words(c.status)}` }),
      markIcon);
  }

  // ---- the note

  function renderDoc(scroll) {
    const pick = $("#note-pick");
    pick.replaceChildren(...S.state.notes.map((note) => el("option", { value: note.file, text: note.file })));
    pick.value = S.note;
    const doc = $("#doc");
    const note = S.state.notes.find((n) => n.file === S.note);
    if (!note) {
      doc.replaceChildren(el("p", { class: "empty", text: "There are no notes in this workspace." }));
      $("#doc-meta").textContent = "";
      return;
    }
    const inNote = claims().filter((c) => c.note === note.file);
    $("#doc-meta").textContent = `${inNote.length} claim${inNote.length === 1 ? "" : "s"}`;
    const out = [];
    let inSources = false;
    for (let i = 0; i < note.lines.length;) {
      const raw = note.lines[i];
      if (raw.trim().startsWith("|")) {
        let j = i;
        while (j < note.lines.length && note.lines[j].trim().startsWith("|")) j += 1;
        out.push(renderTable(note.file, note.lines, i, j));
        i = j;
        continue;
      }
      if (/^#{1,6}\s/.test(raw.trim())) inSources = /^#+\s*(Sources|Gaps and cautions)/i.test(raw.trim());
      out.push(renderLine(note.file, raw, i + 1, inSources));
      i += 1;
    }
    doc.replaceChildren(...out);
    if (scroll) reveal(doc, doc.querySelector(".cur-line"));
  }

  function spansOn(file, line) {
    const spans = [];
    for (const index of S.byLine.get(lineKey(file, line)) || []) {
      const c = claims()[index];
      if (c.start >= 0 && c.end > c.start) spans.push({ start: c.start, end: c.end, claim: index });
    }
    for (const link of S.links.get(lineKey(file, line)) || []) spans.push({ start: link.start, end: link.end, link });
    return spans;
  }

  function gutter(file, line) {
    const whole = (S.byLine.get(lineKey(file, line)) || []).filter((index) => claims()[index].start < 0);
    return [el("span", { class: "no", text: line }), ...whole.map((index) => {
      const c = claims()[index];
      return el("button", { type: "button", class: `gm v-${VCLASS[c.verdict]}${index === S.cur ? " cur" : ""}`, "data-claim": index,
        title: `${CHECKS[c.check] || c.check}: ${VWORD[c.verdict]}, ${words(c.status)}`, "aria-label": `${CHECKS[c.check] || c.check} on line ${line}` });
    })];
  }

  function isCurrentLine(file, line) {
    const c = claim();
    return S.browse === null && c && c.note === file && c.line === line;
  }

  function renderLine(file, raw, line, inSources) {
    const text = raw.trim();
    const classes = ["ln"];
    const heading = /^(#{1,6})\s/.exec(text);
    if (heading) classes.push("h", `h${heading[1].length}`);
    else if (text.startsWith(">")) classes.push("bq");
    if (!text) classes.push("blank");
    if (inSources && !heading) classes.push("src");
    if (isCurrentLine(file, line)) classes.push("cur-line");
    return el("div", { class: classes.join(" "), "data-line": line, id: `L${line}` },
      el("div", { class: "gut" }, gutter(file, line)),
      el("div", { class: "tx" }, marked(raw, 0, raw.length, spansOn(file, line))));
  }

  function renderTable(file, lines, from, to) {
    const divider = /^\s*\|[\s\-:|]+\|\s*$/;
    const rows = [];
    for (let k = from; k < to; k += 1) {
      const raw = lines[k];
      if (divider.test(raw)) continue;
      const line = k + 1;
      const head = k + 1 < to && divider.test(lines[k + 1]);
      const bars = [];
      for (let at = raw.indexOf("|"); at >= 0; at = raw.indexOf("|", at + 1)) {
        if (raw[at - 1] !== "\\") bars.push(at);
      }
      const spans = spansOn(file, line);
      const cells = [];
      for (let b = 0; b + 1 < bars.length; b += 1) {
        cells.push(el(head ? "th" : "td", {}, marked(raw, bars[b] + 1, bars[b + 1], spans)));
      }
      rows.push(el("tr", { "data-line": line, id: `L${line}`, class: isCurrentLine(file, line) ? "cur-line" : null },
        el("td", { class: "gut" }, gutter(file, line)), cells));
    }
    return el("div", { class: "tbl-wrap" }, el("table", { class: "md" }, el("tbody", {}, rows)));
  }

  // raw[from:to], with each claim and link on it marked. Where marks overlap, the narrowest claim shows.
  function marked(raw, from, to, spans) {
    const here = spans.filter((span) => span.end > from && span.start < to);
    if (!here.length) return [raw.slice(from, to)];
    const cuts = new Set([from, to]);
    for (const span of here) {
      cuts.add(Math.max(from, span.start));
      cuts.add(Math.min(to, span.end));
    }
    const points = [...cuts].sort((a, b) => a - b);
    const out = [];
    let last = null;
    for (let k = 0; k + 1 < points.length; k += 1) {
      const [a, b] = [points[k], points[k + 1]];
      const cover = here.filter((span) => span.start <= a && span.end >= b);
      const claimed = cover.filter((span) => span.claim !== undefined).sort((p, q) => (p.end - p.start) - (q.end - q.start));
      const pick = claimed[0] || cover.find((span) => span.link) || null;
      const text = raw.slice(a, b);
      if (pick && last && last.pick === pick) {
        last.node.append(text);
        continue;
      }
      let node;
      if (!pick) node = document.createTextNode(text);
      else if (pick.claim !== undefined) node = claimMark(pick.claim, text);
      else node = el("a", { class: "keylink", href: "#", "data-source": pick.link.sources[0], title: "Open this source" }, text);
      out.push(node);
      last = { pick, node };
    }
    return out;
  }

  function claimMark(index, text) {
    const c = claims()[index];
    const classes = ["hl", `v-${VCLASS[c.verdict]}`];
    if (index === S.cur && S.browse === null) classes.push("cur");
    if (c.mark) classes.push(`m-${c.mark.mark}`);
    if (c.stale) classes.push("stale");
    const said = `${CHECKS[c.check] || c.check}: ${VWORD[c.verdict]}, ${words(c.status)}` + (c.mark ? `. Marked: ${c.mark.mark}` : "");
    return el("mark", { class: classes.join(" "), "data-claim": index, title: said }, text);
  }

  // ---- the source

  function currentView() {
    const c = claim();
    if (S.browse !== null || !c || !c.views.length) return null;
    return c.views[clamp(S.view, 0, c.views.length - 1)];
  }

  async function renderSource(scroll) {
    const head = $("#source-head");
    const tools = $("#source-tools");
    const body = $("#source");
    const c = claim();
    const view = currentView();
    const id = S.browse !== null ? S.browse : (view ? view.source : null);
    const ticket = ++S.ticket;
    head.replaceChildren(sourceTabs(c, id));
    tools.replaceChildren();
    if (id === null) {
      body.replaceChildren(noSource(c));
      return;
    }
    const source = S.state.sources[id];
    head.append(el("div", { class: "src-title", text: source.title || host(source.url) }), sourceMeta(source));
    body.replaceChildren(el("p", { class: "loading", text: "Reading the stored copy…" }));
    let data;
    try {
      data = await getText(id);
    } catch (problem) {
      if (ticket === S.ticket) body.replaceChildren(el("p", { class: "empty", text: problem.message }));
      return;
    }
    if (ticket !== S.ticket) return;
    if (data.text === null || data.text === undefined) {
      body.replaceChildren(el("div", { class: "note-card" }, el("h3", { text: "No text is held for this source" }),
        el("p", { text: view && view.said ? view.said : `Its status is “${source.status}”. Fetch it, or load text gathered by hand, then recheck.` })));
      return;
    }
    drawSource(id, data, view, tools, body, scroll);
  }

  function sourceTabs(c, id) {
    const tabs = el("div", { class: "tabs", role: "tablist", "aria-label": "Sources the claim cites" });
    if (c && S.browse === null) {
      c.views.forEach((view, index) => {
        const source = S.state.sources[view.source];
        tabs.append(el("button", { type: "button", class: "tab", role: "tab", "aria-selected": String(index === clamp(S.view, 0, c.views.length - 1)),
          "data-view": index, title: source.url },
        el("strong", { text: keyFor(source, c.note) }), el("span", { class: "tab-host", text: source.title || host(source.url) }),
        view.hits.length ? null : el("span", { class: "tab-host", text: "· not found" })));
      });
    }
    if (S.browse !== null && c) {
      tabs.append(el("button", { type: "button", class: "btn", "data-back": "1", text: "← Back to the claim" }));
    }
    const picker = el("select", { class: "browse", "aria-label": "Open any source" },
      el("option", { value: "", text: "Open a source…" }),
      S.state.sources.map((source) => el("option", { value: source.id, text: `${source.keys.map((key) => key.split(" ").pop()).join(", ") || "-"} · ${source.title || host(source.url)}` })));
    picker.value = S.browse !== null ? String(S.browse) : "";
    tabs.append(picker);
    return tabs;
  }

  function sourceMeta(source) {
    const good = ["fetched", "gathered by hand", "imported file"].includes(source.status);
    const bad = ["refused", "failed"].includes(source.status);
    return el("div", { class: "src-meta" },
      el("span", { class: `status${good ? " ok" : bad ? " bad" : ""}`, text: source.status }),
      webAddress(source.url)
        ? el("a", { href: source.url, target: "_blank", rel: "noopener noreferrer", title: "Open the address as it is now, in a new tab" }, host(source.url), " ↗")
        : el("code", { text: source.url }),
      source.fetchedAt ? el("span", { text: `kept ${source.fetchedAt.slice(0, 10)}` }) : null,
      source.sha256 ? el("span", { title: `sha256 ${source.sha256}` }, "sha256 ", el("code", { text: source.sha256.slice(0, 12) })) : null,
      source.chars ? el("span", { text: `${source.chars.toLocaleString()} characters` }) : null,
      source.kind ? el("span", { text: source.kind }) : null);
  }

  function noSource(c) {
    if (!c) return el("p", { class: "empty", text: "Choose a claim, or open a source." });
    if (c.working) {
      const w = c.working;
      return el("div", { class: "note-card" },
        el("h3", { text: "Worked out, not taken from a source" }),
        el("p", {}, "The note writes ", el("code", { text: w.stated }), " from ", el("code", { text: w.working }), "."),
        el("p", {}, "The working gives ", el("strong", { text: w.gives || "nothing it can read" }), "."),
        w.inputs.length ? el("p", { class: "muted small", text: w.traced
          ? "Each input is a figure the notes hold from a source, or another working. Open one to see its source:"
          : "Where each input is held in the notes:" }) : null,
        el("div", { class: "inputs" }, w.inputs.map((input) => {
          if (!input.claims.length) return el("span", { class: "tag", text: `${input.text}: not in the notes` });
          return input.claims.map((index) => {
            const held = claims()[index];
            return el("button", { type: "button", class: `btn v-${VCLASS[held.verdict]}`, "data-claim": index, title: `Line ${held.line}: ${VWORD[held.verdict]}` },
              el("span", { class: `dot v-${VCLASS[held.verdict]}` }), `${input.text} · line ${held.line}`);
          });
        })));
    }
    if (c.check === "sections") {
      return el("div", { class: "note-card" }, el("h3", { text: "A section of the note" }), el("p", { text: c.detail }));
    }
    return el("div", { class: "note-card" }, el("h3", { text: "No passage to show" }),
      el("p", { text: c.keys.length ? "The sources this line cites have no address the review knows of." : "This line cites no source." }));
  }

  function snapStart(text, at) {
    if (at <= 0) return 0;
    const before = text.lastIndexOf("\n", at);
    return before < 0 ? 0 : before + 1;
  }

  function snapEnd(text, at) {
    if (at >= text.length) return text.length;
    const after = text.indexOf("\n", at);
    return after < 0 ? text.length : after;
  }

  function pageAt(pages, at) {
    return pages.find(([, start, end]) => start <= at && at < end) || null;
  }

  function drawSource(id, data, view, tools, body, scroll) {
    const text = data.text;
    const hits = view ? view.hits : [];
    S.hit = clamp(S.hit, 0, Math.max(0, hits.length - 1));
    const focus = hits.length ? hits[S.hit][0] : (view && view.region.length ? view.region[0][0] : (view && view.labels.length ? view.labels[0][0] : 0));
    const key = `${id}:${S.cur}:${S.view}:${S.hit}:${S.browse}`;
    if (!S.win || S.win.key !== key) S.win = { key, start: snapStart(text, focus - AROUND), end: snapEnd(text, focus + AROUND) };
    const { start, end } = S.win;

    // The tools: what was found, the places, and the legend.
    if (view) {
      const page = hits.length ? pageAt(data.pages, hits[S.hit][0]) : null;
      const onPage = page ? ` On page ${page[0]}${page[3] && page[3] !== String(page[0]) ? ` (printed ${page[3]})` : ""}.` : "";
      tools.append(el("span", { class: "said", text: (view.said || "") + onPage }));
      if (hits.length > 1) {
        tools.append(el("span", { class: "nav-hits" },
          el("button", { type: "button", class: "icon-btn", "data-hit": "-1", title: "Previous place ([)", "aria-label": "Previous place" }, "‹"),
          `${S.hit + 1} of ${hits.length}`,
          el("button", { type: "button", class: "icon-btn", "data-hit": "1", title: "Next place (])", "aria-label": "Next place" }, "›")));
      }
      tools.append(el("span", { class: "legend" },
        hits.length ? el("span", {}, el("span", { class: "swatch hit" }), hits[0][2] === "closest" ? "Closest passage" : "Where it stands") : null,
        view.labels.length ? el("label", { title: "Words the row describes its figure by (l)" },
          el("input", { type: "checkbox", id: "show-labels", checked: S.showLabels }), el("span", { class: "swatch lbl" }), "The row's words") : null,
        view.region.length ? el("span", {}, el("span", { class: "swatch rg" }), "Page or section cited") : null));
    } else {
      tools.append(el("span", { class: "said", text: "The whole stored copy, as it was kept." }));
    }

    // The text, with each mark.
    const spans = [];
    if (view) {
      hits.forEach(([s, e, how], index) => spans.push({ s, e, cls: `hit${how === "closest" ? " closest" : ""}${index === S.hit ? " cur" : ""}`, hit: index }));
      if (S.showLabels) view.labels.forEach(([s, e]) => spans.push({ s, e, cls: "lbl" }));
      view.region.forEach(([s, e]) => spans.push({ s, e, cls: "rg" }));
    }
    const breaks = data.pages.filter(([, s]) => s > start && s < end);
    const cuts = new Set([start, end, ...breaks.map(([, s]) => s)]);
    const inside = spans.filter((span) => span.e > start && span.s < end);
    for (const span of inside) {
      cuts.add(Math.max(start, span.s));
      cuts.add(Math.min(end, span.e));
    }
    const points = [...cuts].sort((a, b) => a - b);
    const pre = el("div", { class: "stext" });
    const firstPage = pageAt(data.pages, start);
    if (firstPage && data.pages.length > 1) pre.append(pageBreak(firstPage));
    for (let k = 0; k + 1 < points.length; k += 1) {
      const [a, b] = [points[k], points[k + 1]];
      const startsPage = breaks.find(([, s]) => s === a);
      if (startsPage) pre.append(pageBreak(startsPage));
      const cover = inside.filter((span) => span.s <= a && span.e >= b);
      const piece = text.slice(a, b);
      if (!cover.length) {
        pre.append(piece);
        continue;
      }
      const hit = cover.find((span) => span.hit !== undefined);
      pre.append(el("span", { class: [...new Set(cover.flatMap((span) => span.cls.split(" ")))].join(" "),
        "data-hit-at": hit ? hit.hit : null }, piece));
    }
    const out = [];
    if (start > 0) out.push(el("button", { type: "button", class: "btn more", "data-more": "before" }, `Show earlier text (${start.toLocaleString()} characters before)`));
    out.push(pre);
    if (end < text.length) out.push(el("button", { type: "button", class: "btn more", "data-more": "after" }, `Show later text (${(text.length - end).toLocaleString()} characters after)`));
    if (start > 0 || end < text.length) out.push(el("button", { type: "button", class: "linkish more", "data-more": "all" }, "Show the whole text"));
    const before = body.scrollHeight - body.scrollTop;
    body.replaceChildren(...out);
    if (scroll === "keep-bottom") {
      body.scrollTop = body.scrollHeight - before;
    } else if (scroll) {
      const current = pre.querySelector(".hit.cur") || pre.querySelector(".rg") || pre.querySelector(".lbl");
      if (current) reveal(body, current);
      else body.scrollTop = 0;
    }
  }

  function pageBreak([page, , , folio]) {
    return el("div", { class: "page-sep", role: "separator", text: `Page ${page}${folio && folio !== String(page) ? ` · printed ${folio}` : ""}` });
  }

  async function showMore(which) {
    const view = currentView();
    const id = S.browse !== null ? S.browse : (view ? view.source : null);
    if (id === null || !S.win) return;
    const data = await getText(id);
    const text = data.text || "";
    if (which === "before") S.win.start = snapStart(text, S.win.start - MORE);
    else if (which === "after") S.win.end = snapEnd(text, S.win.end + MORE);
    else S.win = { key: S.win.key, start: 0, end: text.length };
    const tools = $("#source-tools");
    tools.replaceChildren();
    drawSource(id, data, view, tools, $("#source"), which === "before" ? "keep-bottom" : false);
  }

  // ---- the claim bar

  function renderBar() {
    const bar = $("#bar");
    const c = claim();
    if (S.form === "edit" && S.editLine) {
      bar.replaceChildren(editForm());
      focusForm();
      return;
    }
    if (!c) {
      bar.replaceChildren(el("p", { class: "why muted", text: claims().length ? "Choose a claim from the list or the note." :
        "Nothing to review yet. The checks judged no claim: cite a source on each row, fetch the sources, then recheck." }));
      return;
    }
    const order = visibleOrder();
    const at = order.indexOf(S.cur);
    const where = [c.line ? `${c.note}, line ${c.line}` : c.note, c.keys.length ? `cites ${c.keys.join(", ")}` : "cites no source"].filter(Boolean).join(" · ");
    const parts = [el("div", { class: "bar-head" },
      el("span", { class: `pill v-${VCLASS[c.verdict]}` }, el("span", { class: `dot v-${VCLASS[c.verdict]}` }), VWORD[c.verdict]),
      el("span", { class: "tag", text: CHECKS[c.check] || c.check }),
      el("span", { class: "bar-item", text: c.item || words(c.status), title: c.item }),
      el("span", { class: "bar-where", text: where }),
      el("span", { class: "bar-nav" },
        el("button", { type: "button", class: "icon-btn", "data-step": "-1", title: "Previous claim (k)", "aria-label": "Previous claim" }, "‹"),
        at >= 0 ? `${at + 1} of ${order.length}` : `not in the list shown`,
        el("button", { type: "button", class: "icon-btn", "data-step": "1", title: "Next claim (j)", "aria-label": "Next claim" }, "›")))];

    const why = [];
    why.push(el("span", { class: "label", text: `${words(c.status)}` }));
    if (c.detail) why.push(": ", c.detail);
    else if (c.verdict === "pass") why.push(": the check found it in what the line cites.");
    parts.push(el("p", { class: "why" }, why));
    if (c.waiver) parts.push(el("p", { class: "why" }, el("span", { class: "label", text: "Waived: " }), c.waiver));
    if (c.mark) {
      parts.push(el("p", { class: `marked ${c.mark.mark}` },
        `${c.mark.mark === "agrees" ? "✓ Marked as matching the source" : "✗ Marked as disagreeing with the source"} by ${c.mark.by} on ${c.mark.on}`,
        c.mark.comment ? `: “${c.mark.comment}”` : ".",
        c.stale ? el("span", { class: "stale-note", text: `Look again: ${c.stale}.` }) : null));
    }
    if (c.suggestion) parts.push(suggestionBox(c.suggestion, c));
    if (S.form === "disagree") parts.push(disagreeForm(c));
    else if (S.form === "accept") parts.push(acceptForm(c));
    else if (S.form === "name") parts.push(nameForm());
    else parts.push(actions(c));
    bar.replaceChildren(...parts);
    focusForm();
  }

  function suggestionBox(s, c) {
    const diff = el("span", { class: "diff" }, s.diff.map(([op, text], index) => {
      const gap = index ? " " : "";
      if (op === "delete") return [gap, el("del", { text })];
      if (op === "insert") return [gap, el("ins", { text })];
      return [gap, text];
    }));
    return el("div", { class: "suggest" },
      el("div", { class: "suggest-head" }, el("strong", { text: `A correction the ${c.check === "arithmetic" ? "working" : "source"} gives` }), diff,
        el("button", { type: "button", class: "btn primary", "data-act": "apply", disabled: S.state.readOnly, title: "Write this line to the note (s)" },
          "Apply", el("kbd", { text: "s" }))),
      el("div", { class: "small", text: s.why }),
      el("div", { class: "will-read" }, `Line ${s.line} would read: `, el("code", { text: s.new.trim() })));
  }

  function actions(c) {
    const locked = S.state.readOnly;
    const agrees = c.mark && c.mark.mark === "agrees" && !c.stale;
    const disagrees = c.mark && c.mark.mark === "disagrees" && !c.stale;
    const acceptable = ["FAIL", "warning"].includes(c.verdict) && ["citations", "quotations", "arithmetic", "numbers", "sections"].includes(c.check);
    return el("div", { class: "actions" },
      el("button", { type: "button", class: `btn good${agrees ? " on" : ""}`, "data-act": "agrees", disabled: locked,
        title: "It says what the source says (a)" }, "✓ Matches source", el("kbd", { text: "a" })),
      el("button", { type: "button", class: `btn bad${disagrees ? " on" : ""}`, "data-act": "disagree", disabled: locked,
        title: "It doesn't say what the source says (d)" }, "✗ Disagrees…", el("kbd", { text: "d" })),
      c.mark ? el("button", { type: "button", class: "btn", "data-act": "clear", disabled: locked, title: "Take the mark away (x)" }, "Clear mark") : null,
      el("span", { class: "sep" }),
      acceptable ? el("button", { type: "button", class: "btn", "data-act": "accept", disabled: locked,
        title: "Accept the finding with a reason: a row of checks/waivers.csv (w)" }, "Accept finding…", el("kbd", { text: "w" })) : null,
      c.line ? el("button", { type: "button", class: "btn", "data-act": "edit", disabled: locked, title: "Edit this line of the note yourself (e)" },
        "Edit line", el("kbd", { text: "e" })) : null,
      S.state.canUndo ? el("button", { type: "button", class: "btn", "data-act": "undo", disabled: locked, title: "Put back the last line changed (u)" },
        "Undo", el("kbd", { text: "u" })) : null);
  }

  function nameField() {
    return el("label", {}, "Your name or initials", el("input", { type: "text", id: "f-by", value: by(), autocomplete: "name", maxlength: "80" }));
  }

  function disagreeForm(c) {
    const current = c.mark && c.mark.mark === "disagrees" ? c.mark.comment : "";
    return el("div", { class: "form", "data-form": "disagree" },
      el("label", {}, "What does the source say instead?",
        el("textarea", { id: "f-comment", placeholder: "The source gives 551.2 for 2025, not 551.1." }, current)),
      nameField(),
      el("div", { class: "row" },
        el("button", { type: "button", class: "btn bad", "data-submit": "disagree" }, "Mark as disagreeing"),
        el("button", { type: "button", class: "btn", "data-cancel": "1" }, "Cancel"),
        el("span", { class: "hint", text: "Ctrl+Enter to save, Esc to cancel. Kept in checks/review.csv." })));
  }

  function acceptForm(c) {
    return el("div", { class: "form", "data-form": "accept" },
      el("label", {}, `Why accept this ${words(c.status)} finding?`,
        el("textarea", { id: "f-reason", placeholder: "Confirmed by phone with the company's press office." })),
      nameField(),
      el("div", { class: "row" },
        el("button", { type: "button", class: "btn primary", "data-submit": "accept" }, "Write the waiver"),
        el("button", { type: "button", class: "btn", "data-cancel": "1" }, "Cancel"),
        el("span", { class: "hint", text: "Adds a row to checks/waivers.csv for this line. It lapses when the line or its source changes." })));
  }

  function nameForm() {
    return el("div", { class: "form", "data-form": "name" }, nameField(),
      el("div", { class: "row" },
        el("button", { type: "button", class: "btn primary", "data-submit": "name" }, "Save and mark"),
        el("button", { type: "button", class: "btn", "data-cancel": "1" }, "Cancel"),
        el("span", { class: "hint", text: "Each mark says who made it. Your name is kept in this browser only." })));
  }

  function editForm() {
    const { note, line } = S.editLine;
    const lines = (S.state.notes.find((n) => n.file === note) || { lines: [] }).lines;
    return el("div", { class: "form", "data-form": "edit" },
      el("label", {}, `Line ${line} of ${note}`,
        el("input", { type: "text", id: "f-line", class: "line-edit", value: lines[line - 1] || "", spellcheck: "true" })),
      el("div", { class: "row" },
        el("button", { type: "button", class: "btn primary", "data-submit": "edit" }, "Save the line"),
        el("button", { type: "button", class: "btn", "data-cancel": "1" }, "Cancel"),
        el("span", { class: "hint", text: "Enter to save, Esc to cancel. The checks run again once it's saved; u puts it back." })));
  }

  function focusForm() {
    const field = $("#bar .form textarea, #bar .form input");
    if (field && document.activeElement !== field) {
      field.focus();
      if (field.id === "f-line") field.setSelectionRange(field.value.length, field.value.length);
    }
  }

  // ---------------------------------------------------------------- what the person does

  function needName(then) {
    if (by()) return false;
    S.pending = then;
    S.form = "name";
    renderBar();
    return true;
  }

  function markAgrees() {
    const c = claim();
    if (!c || S.state.readOnly) return;
    if (needName(markAgrees)) return;
    act("/api/mark", { claim: claimRef(c), mark: "agrees", comment: "", by: by() }, () => {
      if (!S.filters.open) return;
      step(1, true);
    });
  }

  function clearMark() {
    const c = claim();
    if (!c || !c.mark || S.state.readOnly) return;
    act("/api/mark", { claim: claimRef(c), mark: "", comment: "", by: by() });
  }

  function openForm(form) {
    const c = claim();
    if (!c || S.state.readOnly) return;
    if (form === "accept" && !["FAIL", "warning"].includes(c.verdict)) return;
    if (form === "edit") {
      if (!c.line) return;
      S.editLine = { note: c.note, line: c.line };
    }
    S.form = form;
    renderBar();
  }

  function editAnyLine(note, line) {
    if (S.state.readOnly) {
      toast("This is the example workspace: the review doesn't change it.");
      return;
    }
    S.editLine = { note, line };
    S.form = "edit";
    renderBar();
  }

  function submitForm() {
    const c = claim();
    const field = (id) => (document.getElementById(id) || { value: "" }).value;
    if (S.form === "name" || S.form === "disagree" || S.form === "accept") {
      const who = field("f-by").trim();
      if (!who) {
        toast("Say who you are: a name or initials.", { error: true });
        return;
      }
      save("by", who);
    }
    if (S.form === "name") {
      const then = S.pending;
      S.pending = null;
      S.form = null;
      if (then) then();
      else renderBar();
    } else if (S.form === "disagree" && c) {
      act("/api/mark", { claim: claimRef(c), mark: "disagrees", comment: field("f-comment"), by: by() }, () => {
        S.form = null;
        renderBar();
      });
    } else if (S.form === "accept" && c) {
      act("/api/accept", { claim: claimRef(c), reason: field("f-reason"), by: by() }, () => {
        S.form = null;
        renderBar();
        toast("Waiver written to checks/waivers.csv.");
      });
    } else if (S.form === "edit" && S.editLine) {
      const { note, line } = S.editLine;
      const lines = (S.state.notes.find((n) => n.file === note) || { lines: [] }).lines;
      const old = lines[line - 1];
      const value = field("f-line");
      if (value === old) {
        S.form = null;
        S.editLine = null;
        renderBar();
        return;
      }
      act("/api/edit", { note, line, old, new: value }, () => {
        S.form = null;
        S.editLine = null;
        renderBar();
        toast(`Line ${line} of ${note} written, and the checks run again.`, { undo: true });
      });
    }
  }

  function apply() {
    const c = claim();
    if (!c || !c.suggestion || S.state.readOnly) return;
    const s = c.suggestion;
    act("/api/edit", { note: c.note, line: s.line, old: s.old, new: s.new }, () => {
      toast(`Applied to line ${s.line}, and the checks run again.`, { undo: true });
    });
  }

  function undo() {
    if (!S.state.canUndo || S.state.readOnly) return;
    act("/api/undo", {}, () => toast("Put back."));
  }

  function recheck() {
    act("/api/recheck", {}, () => toast("Checked again."));
  }

  let toastTimer = null;
  function toast(message, options = {}) {
    const box = $("#toast");
    box.className = `toast${options.error ? " error" : ""}`;
    box.replaceChildren(...[el("span", { text: message }),
      options.undo ? el("button", { type: "button", class: "linkish", "data-act": "undo" }, "Undo") : null].filter(Boolean));
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      box.hidden = true;
    }, options.error ? 9000 : 6000);
  }

  // ---------------------------------------------------------------- wiring

  function onClick(event) {
    const target = event.target.closest("button, a, mark, input, select, [data-hit-at]");
    if (!target) return;
    const data = target.dataset;
    if (target.matches(".keylink")) {
      event.preventDefault();
      browse(Number(data.source));
      return;
    }
    if (data.claim !== undefined) {
      choose(Number(data.claim));
      $("#queue").classList.remove("open");
      return;
    }
    if (data.verdict !== undefined) {
      if (S.filters.off.has(data.verdict)) S.filters.off.delete(data.verdict);
      else S.filters.off.add(data.verdict);
      saveFilters();
      render({ scroll: false });
      return;
    }
    if (data.view !== undefined) {
      S.view = Number(data.view);
      S.hit = 0;
      S.win = null;
      renderSource(true);
      return;
    }
    if (data.hit !== undefined) {
      moveHit(Number(data.hit));
      return;
    }
    if (data.hitAt !== undefined) {
      S.hit = Number(data.hitAt);
      renderSource(true);
      return;
    }
    if (data.more !== undefined) {
      showMore(data.more);
      return;
    }
    if (data.back !== undefined) {
      S.browse = null;
      S.win = null;
      render({ scroll: true });
      return;
    }
    if (data.step !== undefined) {
      step(Number(data.step));
      return;
    }
    if (data.cancel !== undefined) {
      S.form = null;
      S.editLine = null;
      S.pending = null;
      renderBar();
      return;
    }
    if (data.submit !== undefined) {
      submitForm();
      return;
    }
    const acts = { agrees: markAgrees, disagree: () => openForm("disagree"), clear: clearMark, accept: () => openForm("accept"),
      edit: () => openForm("edit"), apply, undo };
    if (data.act && acts[data.act]) acts[data.act]();
  }

  function moveHit(by) {
    const view = currentView();
    if (!view || !view.hits.length) return;
    S.hit = (S.hit + by + view.hits.length) % view.hits.length;
    renderSource(true);
  }

  function onKey(event) {
    const typing = event.target.matches("input[type=text], textarea, select");
    if (event.key === "Escape") {
      if ($("#help").open) return;
      if (S.form) {
        S.form = null;
        S.editLine = null;
        S.pending = null;
        renderBar();
        event.preventDefault();
      }
      return;
    }
    if (typing) {
      const submit = event.key === "Enter" && (event.ctrlKey || event.metaKey || event.target.matches("input[type=text]"));
      if (submit) {
        event.preventDefault();
        submitForm();
      }
      return;
    }
    if (event.ctrlKey || event.metaKey || event.altKey || !S.state) return;
    const keys = {
      j: () => step(1), k: () => step(-1), ArrowRight: () => step(1), ArrowLeft: () => step(-1),
      J: () => step(1, true), K: () => step(-1, true),
      "]": () => moveHit(1), "[": () => moveHit(-1),
      a: markAgrees, d: () => openForm("disagree"), x: clearMark, s: apply, e: () => openForm("edit"), w: () => openForm("accept"),
      u: undo, r: recheck,
      l: () => {
        S.showLabels = !S.showLabels;
        save("labels", S.showLabels);
        renderSource(false);
      },
      "?": () => $("#help").showModal(),
    };
    if (keys[event.key]) {
      event.preventDefault();
      keys[event.key]();
    }
  }

  function wire() {
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
    $("#doc").addEventListener("dblclick", (event) => {
      const line = event.target.closest("[data-line]");
      if (line && S.note) editAnyLine(S.note, Number(line.dataset.line));
    });
    document.addEventListener("change", (event) => {
      const target = event.target;
      if (target.id === "only-open") {
        S.filters.open = target.checked;
        saveFilters();
        render({ scroll: false });
      } else if (target.id === "group-by") {
        S.filters.group = target.value;
        saveFilters();
        renderQueue(true);
      } else if (target.id === "note-pick") {
        S.note = target.value;
        renderDoc(false);
        $("#doc").scrollTop = 0;
      } else if (target.id === "show-labels") {
        S.showLabels = target.checked;
        save("labels", S.showLabels);
        renderSource(false);
      } else if (target.matches(".browse") && target.value !== "") {
        browse(Number(target.value));
      }
    });
    $("#recheck").addEventListener("click", recheck);
    $("#help-open").addEventListener("click", () => $("#help").showModal());
    $("#help-close").addEventListener("click", () => $("#help").close());
    $("#queue-toggle").addEventListener("click", () => {
      const queue = $("#queue");
      queue.classList.toggle("open");
      $("#queue-toggle").setAttribute("aria-expanded", String(queue.classList.contains("open")));
    });
  }

  async function start() {
    wire();
    $("#doc").replaceChildren(el("p", { class: "loading", text: "Reading the notes and their sources…" }));
    try {
      setState(await api("/api/state"), null, false);
    } catch (problem) {
      $("#doc").replaceChildren(el("p", { class: "empty", text: problem.message }));
    }
  }

  start();
})();
