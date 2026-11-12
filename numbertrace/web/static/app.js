"use strict";
// NumberTrace dashboard. All untrusted text is inserted with textContent (never innerHTML).
(function () {
  const $ = (id) => document.getElementById(id);
  const form = $("form"), go = $("go"), cancelBtn = $("cancel"), statusEl = $("status");
  const provSec = $("providers"), provBody = provSec.querySelector("tbody"), result = $("result");
  let controller = null, lastInvestigation = null;

  function el(tag, text, cls) {
    const e = document.createElement(tag);
    if (text !== undefined && text !== null) e.textContent = String(text);
    if (cls) e.className = cls;
    return e;
  }
  function safeLink(url, text) {
    const a = el("a", text || url);
    if (/^https?:\/\//i.test(url)) a.href = url; else a.removeAttribute("href");
    a.rel = "noopener noreferrer nofollow"; a.target = "_blank";
    return a;
  }

  // Theme toggle (remembered per browser; failures are ignored).
  const root = document.documentElement;
  try { const t = localStorage.getItem("nt-theme"); if (t) root.dataset.theme = t; } catch (_) {}
  $("theme").addEventListener("click", () => {
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("nt-theme", root.dataset.theme); } catch (_) {}
  });

  fetch("/api/v1/config").then((r) => r.json()).then((cfg) => {
    if (cfg.demo) $("demo-banner").hidden = false;
    if (cfg.default_region) $("country").placeholder = cfg.default_region;
    if (cfg.history_enabled) $("history").hidden = false;
  }).catch(() => {});

  $("clear-history").addEventListener("click", async () => {
    const r = await fetch("/api/v1/history", { method: "DELETE" });
    const j = await r.json();
    statusEl.textContent = j.deleted ? "History deleted." : "No history to delete.";
  });

  const providerRows = new Map();
  function updateProvider(s) {
    let tr = providerRows.get(s.name);
    if (!tr) {
      tr = document.createElement("tr");
      for (let i = 0; i < 4; i++) tr.appendChild(document.createElement("td"));
      providerRows.set(s.name, tr); provBody.appendChild(tr);
    }
    const c = tr.children;
    c[0].textContent = s.name;
    c[1].textContent = s.state; c[1].className = "state-" + s.state;
    c[2].textContent = s.state === "running" ? "…" : s.result_count;
    c[3].textContent = s.message || "";
  }

  function list(parent, title, items) {
    parent.appendChild(el("h3", title));
    if (!items || !items.length) { parent.appendChild(el("p", "None.", "muted")); return; }
    const ul = el("ul"); items.forEach((i) => ul.appendChild(el("li", i))); parent.appendChild(ul);
  }

  function renderResult(inv) {
    lastInvestigation = inv;
    result.replaceChildren(); result.hidden = false;
    const n = inv.number, md = n.metadata;
    const notices = el("div", null, "card notice");
    inv.notices.forEach((t) => notices.appendChild(el("div", "• " + t)));
    result.appendChild(notices);

    result.appendChild(el("h2", "Number metadata (offline)"));
    const t = el("table");
    [["E.164", n.e164], ["International", n.international], ["National", n.national],
     ["Valid", n.is_valid ? "yes" : "no"], ["Region", (md.region_code || "unknown") + " " + (md.region_description || "")],
     ["Original carrier", md.carrier || "unknown"], ["Line type", md.line_type], ["Confidence", md.confidence]]
      .forEach(([k, v]) => { const tr = el("tr"); tr.appendChild(el("th", k)); tr.appendChild(el("td", v)); t.appendChild(tr); });
    result.appendChild(t);
    md.limitations.concat(n.warnings).forEach((w) => result.appendChild(el("p", "Note: " + w, "muted")));

    const r = inv.risk, rc = el("div", null, "card");
    rc.appendChild(el("h2", "Risk indicator (about the number, not a person)"));
    const lv = el("p"); lv.appendChild(document.createTextNode("Level: "));
    lv.appendChild(el("strong", r.level, "lvl-" + r.level)); lv.appendChild(document.createTextNode(" · score " + r.score + "/100"));
    rc.appendChild(lv);
    const ul = el("ul"); r.reasons.forEach((x) => ul.appendChild(el("li", (x.weight > 0 ? "+" : "") + x.weight + " " + x.factor + ": " + x.detail)));
    rc.appendChild(ul); rc.appendChild(el("p", r.uncertainty)); rc.appendChild(el("p", r.disclaimer, "muted"));
    result.appendChild(rc);

    const s = inv.summary;
    result.appendChild(el("h2", "Evidence summary"));
    list(result, "Observed", s.observed); list(result, "Still unknown", s.unknown);
    list(result, "Conflicting clues", s.conflicts); list(result, "Suggested safe next steps", s.next_steps);

    if (inv.reputation.length) {
      result.appendChild(el("h2", "Community reports"));
      inv.reputation.forEach((rep) => {
        const c = el("div", null, "card");
        if (rep.synthetic) c.appendChild(el("span", "SYNTHETIC", "tag"));
        c.appendChild(el("span", rep.status, "tag"));
        c.appendChild(el("div", rep.category + " — " + rep.source + " (" + rep.report_count + " report(s))"));
        c.appendChild(el("div", rep.summary, "muted"));
        result.appendChild(c);
      });
    }

    result.appendChild(el("h2", "Public web references"));
    let total = 0;
    Object.entries(inv.findings).forEach(([cat, items]) => {
      if (!items.length) return; total += items.length;
      result.appendChild(el("h3", cat + " (" + items.length + ")"));
      items.forEach((f) => {
        const c = el("div", null, "card");
        c.appendChild(el("span", f.status, "tag"));
        c.appendChild(safeLink(f.url, f.title));
        c.appendChild(el("div", f.snippet, "muted"));
        c.appendChild(el("small", "via " + f.provider + " · variant " + f.search_variant, "muted"));
        if (f.warning) c.appendChild(el("p", "⚠ " + f.warning));
        result.appendChild(c);
      });
    });
    if (!total) result.appendChild(el("p", "No web references collected (offline, no API key, or no results). Use the manual links below.", "muted"));

    result.appendChild(el("h2", "Manual search links (open yourself)"));
    const ml = el("ul");
    inv.manual_links.forEach((m) => { const li = el("li", m.engine + ": "); li.appendChild(safeLink(m.url, m.query)); ml.appendChild(li); });
    result.appendChild(ml);

    const row = el("div", null, "row");
    const bh = el("button", "Download HTML report"); bh.type = "button"; bh.addEventListener("click", () => download("html"));
    const bj = el("button", "Download JSON report"); bj.type = "button"; bj.addEventListener("click", () => download("json"));
    row.appendChild(bh); row.appendChild(bj); result.appendChild(row);
  }

  async function download(kind) {
    if (!lastInvestigation) return;
    const r = await fetch("/api/v1/report/" + kind, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(lastInvestigation),
    });
    if (!r.ok) { statusEl.textContent = "Report export failed."; return; }
    const blob = await r.blob(), a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "numbertrace-report." + kind; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  function setBusy(busy) { go.disabled = busy; cancelBtn.disabled = !busy; }

  cancelBtn.addEventListener("click", () => { if (controller) controller.abort(); });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const number = $("number").value.trim(), country = $("country").value.trim().toUpperCase();
    if (!number) return;
    provBody.replaceChildren(); providerRows.clear(); result.hidden = true; provSec.hidden = false;
    statusEl.className = ""; statusEl.textContent = "Starting investigation…";
    controller = new AbortController(); setBusy(true);
    const body = { number, online: $("online").checked };
    if (country) body.country = country;
    try {
      const resp = await fetch("/api/v1/investigate/stream", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: controller.signal,
      });
      if (!resp.ok) {
        const j = await resp.json().catch(() => ({}));
        throw new Error(j.detail || j.error || ("HTTP " + resp.status));
      }
      const reader = resp.body.getReader(), dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, idx); buf = buf.slice(idx + 1);
          if (!line.trim()) continue;
          const evt = JSON.parse(line);
          if (evt.type === "normalized") statusEl.textContent = "Number parsed. Querying providers…";
          else if (evt.type === "provider") updateProvider(evt.status);
          else if (evt.type === "result") { statusEl.textContent = "Done."; renderResult(evt.investigation); }
          else if (evt.type === "error") throw new Error(evt.message);
        }
      }
    } catch (e) {
      statusEl.className = "error";
      statusEl.textContent = e.name === "AbortError" ? "Cancelled. Running provider requests were stopped." : "Error: " + e.message;
    } finally { setBusy(false); controller = null; }
  });
})();
