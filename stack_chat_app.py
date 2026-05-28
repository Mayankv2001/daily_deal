"""FastAPI chat/API surface for the AI deal-stacking agent."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from stack_agent import StackAgent


app = FastAPI(title="AI Deal-Stacking Agent", version="0.1.0")
agent = StackAgent()


class StackSearchRequest(BaseModel):
    query: str = Field(default="", description="Product, retailer, or deal search text")
    url: str | None = Field(default=None, description="Optional product or deal URL")
    max_results: int = Field(default=5, ge=1, le=10)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/stack-search")
def stack_search(payload: StackSearchRequest) -> dict[str, Any]:
    try:
        result = agent.search(payload.query, url=payload.url, max_results=payload.max_results)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.to_dict()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return HTML


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Deal-Stacking Agent</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f6f8;
      --panel: #ffffff;
      --ink: #18202b;
      --muted: #657080;
      --line: #d7dce3;
      --accent: #0f766e;
      --accent-dark: #0b5f59;
      --warn: #9a5b00;
      --risk: #b42318;
      --ok: #087443;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    main {
      min-height: 100vh;
      display: grid;
      grid-template-rows: auto 1fr;
    }
    header {
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      padding: 16px 22px;
    }
    h1 {
      margin: 0;
      font-size: 20px;
      line-height: 26px;
      font-weight: 720;
    }
    .shell {
      width: min(1120px, calc(100vw - 32px));
      margin: 0 auto;
    }
    .workspace {
      display: grid;
      grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
      gap: 18px;
      padding: 18px 0 28px;
    }
    form {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      align-self: start;
    }
    label {
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin: 0 0 6px;
      font-weight: 650;
    }
    input, textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 11px;
      font: inherit;
      color: var(--ink);
      background: #fff;
      min-height: 40px;
    }
    textarea {
      min-height: 96px;
      resize: vertical;
    }
    .field { margin-bottom: 12px; }
    .row {
      display: grid;
      grid-template-columns: 1fr 100px;
      gap: 10px;
      align-items: end;
    }
    button {
      width: 100%;
      border: 0;
      border-radius: 6px;
      min-height: 42px;
      padding: 10px 12px;
      font: inherit;
      font-weight: 720;
      color: #fff;
      background: var(--accent);
      cursor: pointer;
    }
    button:hover { background: var(--accent-dark); }
    button:disabled { opacity: .62; cursor: wait; }
    .results {
      display: grid;
      gap: 12px;
      align-content: start;
    }
    .empty {
      border: 1px dashed var(--line);
      border-radius: 8px;
      padding: 24px;
      color: var(--muted);
      background: rgba(255, 255, 255, .58);
    }
    .rec {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    .rec-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
      border-bottom: 1px solid var(--line);
      padding-bottom: 10px;
      margin-bottom: 10px;
    }
    .rec-title {
      margin: 0 0 4px;
      font-size: 17px;
      line-height: 23px;
      font-weight: 750;
    }
    .meta {
      color: var(--muted);
      font-size: 13px;
      line-height: 18px;
    }
    .saving {
      text-align: right;
      min-width: 140px;
      font-weight: 750;
      color: var(--ok);
    }
    .risk-high { color: var(--risk); }
    .risk-medium { color: var(--warn); }
    .risk-low { color: var(--ok); }
    ol, ul {
      margin: 8px 0 0 20px;
      padding: 0;
      line-height: 22px;
    }
    li { margin: 4px 0; }
    a { color: #155eef; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .section-title {
      margin: 12px 0 0;
      font-size: 12px;
      text-transform: uppercase;
      color: var(--muted);
      font-weight: 800;
    }
    .error {
      border-left: 3px solid var(--warn);
      padding: 8px 10px;
      background: #fff8eb;
      color: #6b4000;
      border-radius: 4px;
      font-size: 13px;
    }
    @media (max-width: 820px) {
      .workspace { grid-template-columns: 1fr; }
      .row { grid-template-columns: 1fr; }
      .rec-head { display: block; }
      .saving { text-align: left; margin-top: 8px; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div class="shell">
        <h1>AI Deal-Stacking Agent</h1>
      </div>
    </header>
    <section class="shell workspace">
      <form id="search-form">
        <div class="field">
          <label for="query">Product or retailer</label>
          <textarea id="query" name="query" placeholder="MacBook Air M4, iPad Air, The Good Guys fridge"></textarea>
        </div>
        <div class="field">
          <label for="url">Product or deal URL</label>
          <input id="url" name="url" type="url" placeholder="https://...">
        </div>
        <div class="row">
          <div class="field">
            <label for="max-results">Results</label>
            <select id="max-results" name="max_results">
              <option value="3">3</option>
              <option value="5" selected>5</option>
              <option value="8">8</option>
            </select>
          </div>
          <button id="submit" type="submit">Search</button>
        </div>
      </form>
      <div class="results" id="results">
        <div class="empty">Search a product to see stack routes, effective savings, risk, and source links.</div>
      </div>
    </section>
  </main>
  <script>
    const form = document.querySelector("#search-form");
    const results = document.querySelector("#results");
    const button = document.querySelector("#submit");

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      button.disabled = true;
      button.textContent = "Searching";
      results.innerHTML = '<div class="empty">Checking live deal, gift card, points, and cashback sources...</div>';

      const payload = {
        query: document.querySelector("#query").value.trim(),
        url: document.querySelector("#url").value.trim() || null,
        max_results: Number(document.querySelector("#max-results").value || 5)
      };

      try {
        const response = await fetch("/api/stack-search", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Search failed");
        render(data);
      } catch (error) {
        results.innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
      } finally {
        button.disabled = false;
        button.textContent = "Search";
      }
    });

    function render(data) {
      const errors = (data.source_errors || []).map(error => `<div class="error">${escapeHtml(error)}</div>`).join("");
      const recs = (data.recommendations || []).map(renderRec).join("");
      results.innerHTML = errors + (recs || '<div class="empty">No recommendations returned.</div>');
    }

    function renderRec(rec) {
      const saving = rec.estimated_saving || {};
      const amount = saving.amount == null ? "" : ` / $${Number(saving.amount).toFixed(2)}`;
      const riskClass = `risk-${rec.risk_level || "medium"}`;
      const base = rec.base_deal || {};
      const baseLink = base.url ? `<a href="${escapeAttr(base.url)}" target="_blank" rel="noreferrer">${escapeHtml(base.title || base.url)}</a>` : escapeHtml(base.title || "");
      return `
        <article class="rec">
          <div class="rec-head">
            <div>
              <h2 class="rec-title">${escapeHtml(rec.title)}</h2>
              <div class="meta">${escapeHtml(rec.retailer)} · ${escapeHtml(base.source || "")} · ${baseLink}</div>
            </div>
            <div class="saving">
              ${Number(saving.percent || 0).toFixed(1)}%${amount}
              <div class="meta">${escapeHtml(saving.confidence || "low")} confidence</div>
              <div class="${riskClass}">${escapeHtml(rec.risk_level || "medium")} risk</div>
            </div>
          </div>
          <div class="section-title">Stack steps</div>
          <ol>${(rec.stack_steps || []).map(step => `<li>${escapeHtml(step)}</li>`).join("")}</ol>
          <div class="section-title">Warnings</div>
          <ul>${(rec.warnings || []).map(warning => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>
          <div class="section-title">Sources</div>
          <div class="meta">${(rec.sources || []).map(escapeHtml).join(", ")}</div>
        </article>
      `;
    }

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
      }[char]));
    }

    function escapeAttr(value) {
      return escapeHtml(value).replace(/`/g, "&#096;");
    }
  </script>
</body>
</html>"""
