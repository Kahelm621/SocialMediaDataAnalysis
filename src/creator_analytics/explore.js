/* YouTube explorer and the extra blocks on My channels.
   Reads the global DATA object when a function runs, not when this file loads. */
(function () {
  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function compact(value) {
    if (value == null || Number.isNaN(value)) return "—";
    return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value);
  }

  function pct(value) {
    if (value == null || Number.isNaN(value)) return "—";
    return Math.round(value * 100) + "%";
  }

  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Outfit, Segoe UI, sans-serif", color: "#241c16", size: 12 },
    margin: { t: 24, r: 16, b: 48, l: 56 },
    legend: { orientation: "h", y: -0.25 },
    xaxis: { gridcolor: "#eadfce", tickformat: "%b %d" },
    yaxis: { gridcolor: "#eadfce" },
  };

  function draw(div, traces, yTitle) {
    if (!div) return;
    if (typeof Plotly !== "undefined") Plotly.purge(div);
    div.replaceChildren();
    if (!traces.length) {
      div.append(el("p", "Nothing in this filter yet.", "empty"));
      return;
    }
    if (typeof Plotly === "undefined") {
      div.textContent = "Charts did not load. Check your connection and refresh.";
      return;
    }
    Plotly.react(div, traces, Object.assign({}, layout, { yaxis: Object.assign({}, layout.yaxis, { title: yTitle }) }), {
      responsive: true,
      displayModeBar: false,
    });
  }

  function explorer() {
    return (window.DATA && window.DATA.explorer) || {};
  }

  function selectedRegion() {
    const node = document.getElementById("explore-region");
    return node ? node.value : "US";
  }

  function selectedCategory() {
    const node = document.getElementById("explore-category");
    return node ? node.value : "0";
  }

  function fillExploreFilters() {
    const data = explorer();
    const region = document.getElementById("explore-region");
    const category = document.getElementById("explore-category");
    if (!region || !category || region.options.length) return;
    (data.regions || []).forEach(function (code) {
      region.append(new Option(code, code));
    });
    (data.categories || []).forEach(function (item) {
      category.append(new Option(item.name, String(item.id)));
    });
    if ((data.regions || []).indexOf("US") !== -1) region.value = "US";
  }

  function renderQuota() {
    const holder = document.getElementById("quota");
    const plan = explorer().quota;
    if (!holder || !plan) return;
    holder.replaceChildren();
    holder.append(el("h3", "YouTube quota plan"));
    holder.append(el("p", plan.note, "section-note"));
    const summary = el(
      "p",
      "About " + plan.estimated_units_per_day + " units per day with this config. Daily stop is " +
        plan.daily_budget + ". The free cap is " + plan.free_quota + "."
    );
    if (plan.over_budget) summary.append(document.createTextNode(" This plan is over the stop line. Search less often or shorten the watchlist."));
    holder.append(summary);
    const table = document.createElement("table");
    const head = document.createElement("tr");
    ["Call", "Units each", "Times / day", "Units / day"].forEach(function (label) {
      head.append(el("th", label));
    });
    table.append(head);
    (plan.lines || []).forEach(function (line) {
      const row = document.createElement("tr");
      [line.item, String(line.units_each), String(line.times_per_day), String(line.units_per_day)].forEach(function (value) {
        row.append(el("td", value));
      });
      table.append(row);
    });
    const wrap = el("div", null, "table-wrap");
    wrap.append(table);
    holder.append(wrap);
  }

  function renderTrending() {
    const data = explorer();
    const region = selectedRegion();
    const category = selectedCategory();
    const rows = (data.trending || []).filter(function (row) {
      return row.region === region && String(row.category_id) === String(category);
    });
    rows.sort(function (a, b) { return (b.views || 0) - (a.views || 0); });
    const body = document.getElementById("trending-body");
    if (!body) return;
    body.replaceChildren();
    document.getElementById("pace-note").textContent = data.pace_note || "";
    rows.forEach(function (row) {
      const tr = document.createElement("tr");
      tr.append(el("td", row.title));
      tr.append(el("td", row.channel_title));
      tr.append(el("td", compact(row.views)));
      tr.append(el("td", compact(row.lifetime_views_per_hour)));
      tr.append(el("td", compact(row.snapshot_views_per_hour)));
      tr.append(el("td", row.is_short ? "Short" : row.is_short == null ? "—" : "Long"));
      tr.append(el("td", row.duration_seconds == null ? "—" : row.duration_seconds + "s"));
      tr.append(el("td", String(row.streak || 0)));
      tr.append(el("td", (row.tags || []).join(", ") || "—"));
      body.append(tr);
    });
    if (!rows.length) {
      const tr = document.createElement("tr");
      const cell = el("td", "No trending rows in this filter.");
      cell.colSpan = 9;
      tr.append(cell);
      body.append(tr);
    }
  }

  function renderPatternCharts() {
    const data = explorer();
    const region = selectedRegion();
    const category = selectedCategory();
    const patterns = (data.title_patterns_over_time || []).filter(function (row) {
      return row.region === region && String(row.category_id) === String(category);
    }).sort(function (a, b) { return a.collected_at < b.collected_at ? -1 : 1; });
    const shorts = (data.shorts_over_time || []).filter(function (row) {
      return row.region === region && String(row.category_id) === String(category);
    }).sort(function (a, b) { return a.collected_at < b.collected_at ? -1 : 1; });
    function trace(name, key, scale) {
      return {
        type: "scatter",
        mode: "lines+markers",
        name: name,
        x: patterns.map(function (row) { return row.collected_at; }),
        y: patterns.map(function (row) { return row[key] == null ? null : row[key] * (scale || 1); }),
      };
    }
    draw(document.getElementById("pattern-chart"), [
      trace("Numbers %", "pct_number", 100),
      trace("Mostly caps %", "pct_caps", 100),
      trace("Emoji %", "pct_emoji", 100),
      trace("Question mark %", "pct_question", 100),
    ], "Share of titles");
    draw(document.getElementById("shorts-chart"), [{
      type: "scatter",
      mode: "lines+markers",
      name: "Shorts share",
      x: shorts.map(function (row) { return row.collected_at; }),
      y: shorts.map(function (row) { return row.short_share == null ? null : row.short_share * 100; }),
    }], "Shorts %");
    const note = document.getElementById("shorts-note");
    if (note) note.textContent = data.shorts_note || "";
  }

  function renderBoards() {
    const data = explorer();
    const region = selectedRegion();
    const category = selectedCategory();
    const topics = document.getElementById("topics");
    const channels = document.getElementById("top-channels");
    if (!topics || !channels) return;
    topics.replaceChildren();
    channels.replaceChildren();
    const topicRows = (data.topics || []).filter(function (row) {
      return row.region === region && String(row.category_id) === String(category);
    });
    if (!topicRows.length) topics.append(el("p", "No rising wording in this chart yet.", "empty"));
    topicRows.forEach(function (row) {
      const card = el("div", null, "change " + row.label);
      const pct = row.pct_change == null ? row.label : (row.pct_change > 0 ? "+" : "") + row.pct_change.toFixed(0) + "%";
      card.append(el("strong", row.term + " · " + pct));
      card.append(el("div", row.previous + " → " + row.current + " titles or tags"));
      topics.append(card);
    });
    const channelRows = (data.top_channels || []).filter(function (row) {
      return row.region === region && String(row.category_id) === String(category);
    });
    if (!channelRows.length) channels.append(el("p", "No channels in this chart yet.", "empty"));
    channelRows.forEach(function (row) {
      channels.append(el("div", row.channel_title + " · " + row.appearances + " video" + (row.appearances === 1 ? "" : "s"), "change"));
    });
  }

  function renderResearch() {
    const rows = explorer().research || [];
    const grouped = new Map();
    rows.forEach(function (row) {
      if (!grouped.has(row.keyword)) grouped.set(row.keyword, []);
      grouped.get(row.keyword).push(row);
    });
    const traces = [];
    let formula = "";
    grouped.forEach(function (points, keyword) {
      points.sort(function (a, b) { return a.collected_at < b.collected_at ? -1 : 1; });
      formula = points[points.length - 1].formula || formula;
      traces.push({
        type: "scatter",
        mode: "lines+markers",
        name: keyword,
        x: points.map(function (point) { return point.collected_at; }),
        y: points.map(function (point) { return point.opportunity_score; }),
      });
    });
    draw(document.getElementById("opportunity-chart"), traces, "Opportunity (estimate)");
    const note = document.getElementById("opportunity-note");
    if (note) note.textContent = formula;
    const body = document.getElementById("research-body");
    if (!body) return;
    body.replaceChildren();
    const latest = [];
    grouped.forEach(function (points) {
      latest.push(points[points.length - 1]);
    });
    latest.sort(function (a, b) { return (b.opportunity_score || 0) - (a.opportunity_score || 0); });
    latest.forEach(function (row) {
      const tr = document.createElement("tr");
      [
        row.keyword,
        row.opportunity_score == null ? "—" : String(row.opportunity_score),
        row.demand_score == null ? "—" : String(row.demand_score),
        row.competition_score == null ? "—" : String(row.competition_score),
        compact(row.median_views),
        compact(row.median_subscribers),
        (row.suggestions || []).join(", ") || "—",
      ].forEach(function (value) { tr.append(el("td", value)); });
      body.append(tr);
    });
  }

  function renderOutliers() {
    const holder = document.getElementById("outliers");
    if (!holder) return;
    holder.replaceChildren();
    const rows = explorer().outliers || [];
    if (!rows.length) {
      holder.append(el("p", "No video in the latest snapshot is at least 3× its channel median.", "empty"));
      return;
    }
    rows.forEach(function (row) {
      const card = el("div", null, "change rising");
      card.append(el("strong", row.multiple + "× · " + row.title));
      card.append(el("div", row.account_name + " · " + compact(row.views) + " views vs median " + compact(row.median_views)));
      card.append(el("p", row.note, "section-note"));
      holder.append(card);
    });
  }

  function renderIdeas() {
    const holder = document.getElementById("ideas");
    if (!holder) return;
    holder.replaceChildren();
    (explorer().ideas || []).forEach(function (idea) {
      const card = el("article", null, "rec");
      card.append(el("h3", idea.headline));
      card.append(el("p", idea.why));
      card.append(el("p", "Try this: " + idea.try_this, "try"));
      holder.append(card);
    });
  }

  function renderSeo() {
    const holder = document.getElementById("seo");
    if (!holder) return;
    holder.replaceChildren();
    const rows = explorer().video_seo || [];
    if (!rows.length) {
      holder.append(el("p", "SEO scores show up after a YouTube snapshot that includes titles, descriptions, and tags.", "empty"));
      return;
    }
    rows.forEach(function (row) {
      const card = el("article", null, "rec");
      card.append(el("h3", row.score + " / 100 · " + row.title));
      card.append(el("p", row.account_name, "section-note"));
      (row.checks || []).filter(function (check) { return !check.ok; }).forEach(function (check) {
        card.append(el("p", check.name + ": " + check.fix));
      });
      if ((row.checks || []).every(function (check) { return check.ok; })) {
        card.append(el("p", "Every check passed for this video."));
      }
      holder.append(card);
    });
  }

  function renderAudit() {
    const holder = document.getElementById("audit");
    if (!holder) return;
    holder.replaceChildren();
    (explorer().audit || []).forEach(function (row) {
      const card = el("article", null, "card");
      card.append(el("div", row.account_name, "label"));
      card.append(el("div", compact(row.followers), "value"));
      card.append(el("div", "Average SEO " + (row.average_seo == null ? "—" : row.average_seo), "hint"));
      card.append(el("div", "Median days between uploads: " + (row.median_days_between_uploads == null ? "—" : row.median_days_between_uploads), "hint"));
      if (row.weakest_check) {
        card.append(el("div", "Most missed check: " + row.weakest_check.name + " (" + row.weakest_check.videos + " videos)", "hint"));
      }
      if (row.top_title) card.append(el("div", "Top video in this snapshot: " + row.top_title + " · " + compact(row.top_views), "hint"));
      holder.append(card);
    });
  }

  function renderCompetitors() {
    const holder = document.getElementById("competitors");
    if (!holder) return;
    holder.replaceChildren();
    const rows = explorer().competitors || [];
    if (!rows.length) {
      holder.append(el("p", "No competitor snapshots yet. The demo includes sample channels. A live run needs enabled competitors in config/tracked.yaml.", "empty"));
      return;
    }
    const traces = rows.map(function (row) {
      return {
        type: "scatter",
        mode: "lines+markers",
        name: row.account_name,
        x: (row.followers_over_time || []).map(function (point) { return point.collected_at; }),
        y: (row.followers_over_time || []).map(function (point) { return point.followers; }),
      };
    });
    const chart = document.getElementById("competitor-chart");
    draw(chart, traces, "Followers");
    rows.forEach(function (row) {
      holder.append(el(
        "p",
        row.account_name + " · " + compact(row.followers) + " subscribers · upload gap " +
          (row.median_days_between_uploads == null ? "—" : row.median_days_between_uploads + " days") +
          " · top video " + (row.top_title || "—") + " (" + compact(row.top_views) + " views)"
      ));
    });
  }

  window.renderMineExtras = function () {
    renderSeo();
    renderAudit();
    renderCompetitors();
    renderIdeas();
  };

  window.renderExplorer = function () {
    fillExploreFilters();
    renderQuota();
    renderTrending();
    renderPatternCharts();
    renderBoards();
    renderResearch();
    renderOutliers();
  };

  document.addEventListener("change", function (event) {
    if (event.target && (event.target.id === "explore-region" || event.target.id === "explore-category")) {
      renderTrending();
      renderPatternCharts();
      renderBoards();
    }
  });
})();
