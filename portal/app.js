/* A local, read-only viewer. Model inference and evidence gates run in the exporter. */
"use strict";

(() => {
  const $ = (selector) => document.querySelector(selector);
  const state = { manifest: null, players: [], filtered: [], player: null, detail: null, sport: null, role: null, source: "all", search: "", request: 0 };
  const cache = new Map();
  const list = $("#player-list");
  const panel = $("#player-panel");
  const names = { nfl: "NFL", nba: "NBA", nhl: "NHL", epl: "Premier League" };
  const expertNames = { baseline50: "Midpoint baseline", archetype: "Physical archetypes", ridge: "Linear model", hist_gradient_boosting: "Gradient boosting", extra_trees: "Randomized trees", shared: "Shared-sport model", shared_expert: "Shared-sport model" };
  const statusCopy = {
    no_evidence: ["No supported rating", "This role model has not passed the project’s predictive evidence checks. A physique alone does not justify a rating."],
    out_of_domain: ["Build outside reference range", "This athlete’s height and weight lie outside the model’s supported body domain for this role. Extrapolating would be unreliable."],
    data_review: ["Data under review", "Premier League defender ratings are withheld while incomplete source block-event coverage is reviewed."],
    missing_measurements: ["Measurements unavailable", "Both a usable height and weight are needed. Missing measurements are not filled with a fictional athlete profile."],
    insufficient_support: ["Not enough reference data", "There are too few eligible reference athletes to fit a supported model for this role."],
    unsupported_profile: ["Profile outside model scope", "These models describe adult elite athletes. A known under-18 profile is outside their supported scope."],
    unsupported_role: ["Role not modeled", "This athlete’s source role does not have a fitted possession-winning model."],
  };

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  }
  function add(parent, ...children) {
    children.filter(Boolean).forEach((child) => parent.append(child));
    return parent;
  }
  function finite(value) { return typeof value === "number" && Number.isFinite(value); }
  function fmt(value, digits = 0) { return finite(value) ? value.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits }) : "—"; }
  function percent(value, digits = 1) { return finite(value) ? `${fmt(value * 100, digits)}%` : "—"; }
  function league(id) { return state.manifest?.sports.find((sport) => sport.id === id); }
  function leagueLabel(id) { return names[id] || league(id)?.label || id || "Unknown league"; }
  function roleLabel(sport, role) { return league(sport)?.roles?.find((item) => item.id === role)?.label || String(role || "Unclassified").replaceAll("_", " "); }
  function safeWords(value) { return String(value || "").replaceAll("_", " "); }
  function searchText(value) { return String(value || "").normalize("NFD").replace(/\p{Diacritic}/gu, "").toLocaleLowerCase(); }
  function initials(name) { return String(name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase(); }
  function announce(text) { $("#app-announcement").textContent = text; }
  function headFor(result) { return state.manifest.heads?.[result?.head || `${state.sport}:${state.role}`] || {}; }
  function isReview(result, head) { return result?.status === "data_review" || Boolean(head.data_review) || (state.sport === "epl" && state.role === "DEF"); }
  function effectiveStatus(result, head) {
    if (state.player && finite(state.player.age) && state.player.age < 18) return "unsupported_profile";
    if (isReview(result, head)) return "data_review";
    if (!result) return "insufficient_support";
    if (result.out_of_domain === true && result.status === "provisional") return "out_of_domain";
    if (result.status === "provisional" && !finite(result.efficacy_rating)) return "no_evidence";
    return result.status || "no_evidence";
  }
  function availableRoles(sport) {
    const declared = league(sport)?.roles || [];
    const actual = state.detail?.sport_results?.[sport]?.roles || [];
    return declared.length ? declared : actual.map((result) => ({ id: result.role, label: result.role_label || result.role, head: result.head }));
  }
  function selectDefaultRole(sport) {
    const roles = availableRoles(sport);
    const native = state.player?.sport === sport && roles.find((role) => role.id === state.player.role);
    if (native) return native.id;
    const preferred = state.detail?.sport_results?.[sport]?.default_role;
    return roles.find((role) => role.id === preferred)?.id || roles[0]?.id || null;
  }
  function selectedResult() { return state.detail?.sport_results?.[state.sport]?.roles?.find((result) => result.role === state.role); }

  async function fetchJson(path, signal) {
    // Only local exports are allowed, including when hosted below a private site path.
    const url = new URL(path, document.baseURI);
    if (url.origin !== window.location.origin || !url.pathname.startsWith(new URL("data/", document.baseURI).pathname)) throw new Error("The player export path is not local to this project.");
    const response = await fetch(url, { signal, cache: "no-store", credentials: "same-origin" });
    if (!response.ok) throw new Error(`The local data export could not be read (${response.status}).`);
    return response.json();
  }

  function renderList() {
    const query = searchText(state.search.trim());
    state.filtered = state.players.filter((player) => (state.source === "all" || player.sport === state.source) && (!query || searchText(`${player.name} ${player.team || ""}`).includes(query)));
    $("#player-count").textContent = state.filtered.length.toLocaleString("en-US");
    list.replaceChildren();
    if (!state.filtered.length) {
      add(list, node("p", "list-message", "No athletes match this search. Try another name, team or league."));
      return;
    }
    const fragment = document.createDocumentFragment();
    state.filtered.forEach((player) => {
      const button = node("button", "player-option");
      button.type = "button";
      button.dataset.playerId = player.id;
      button.setAttribute("aria-pressed", String(player.id === state.player?.id));
      button.setAttribute("aria-label", `${player.name}, ${player.team || "team unavailable"}, ${leagueLabel(player.sport)}`);
      const copy = node("span", "player-option-copy");
      add(copy, node("span", "player-option-name", player.name), node("span", "player-option-meta", `${player.team || "Team unavailable"} · ${player.sport.toUpperCase()}`));
      const avatar = node("span", "player-initials", initials(player.name));
      avatar.setAttribute("aria-hidden", "true");
      add(button, avatar, copy);
      button.addEventListener("click", () => selectPlayer(player));
      fragment.append(button);
    });
    list.append(fragment);
  }

  function updateSelection() {
    list.querySelectorAll("button[data-player-id]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.playerId === state.player?.id)));
  }

  async function selectPlayer(player, initialSport) {
    const request = ++state.request;
    state.player = player;
    state.detail = null;
    state.sport = initialSport && league(initialSport) ? initialSport : player.sport;
    updateSelection();
    panel.setAttribute("aria-busy", "true");
    panel.replaceChildren(add(node("div", "loading-state"), node("span", "loading-dot"), node("p", "", `Loading ${player.name}…`)));
    try {
      let detail = cache.get(player.id);
      if (!detail) {
        detail = await fetchJson(player.detail_path);
        cache.set(player.id, detail);
      }
      if (request !== state.request) return;
      state.detail = detail;
      state.role = selectDefaultRole(state.sport);
      renderPlayer();
      updateUrl();
      announce(`${player.name} selected. Showing ${leagueLabel(state.sport)} ${roleLabel(state.sport, state.role)} comparison.`);
    } catch (error) {
      if (request !== state.request) return;
      const box = node("div", "panel-error");
      add(box, node("h2", "", "This player could not be loaded"), node("p", "", "The saved result may be missing or the connection may have been interrupted."));
      const retry = node("button", "", "Try again");
      retry.type = "button";
      retry.addEventListener("click", () => selectPlayer(player));
      add(box, retry);
      panel.replaceChildren(box);
      panel.setAttribute("aria-busy", "false");
      announce("The player result could not be loaded. A retry button is available.");
    }
  }

  function updateUrl() {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("player", state.player.id);
      url.searchParams.set("sport", state.sport);
      window.history.replaceState(null, "", url);
    } catch (_) { /* The explorer also works in contexts without History access. */ }
  }

  function renderHeader() {
    const player = state.player;
    const header = node("header", "athlete-header");
    add(header, add(node("div", "athlete-topline"), node("p", "eyebrow", "The athlete"), node("span", "athlete-number", "PHYSICAL PROFILE")), node("h2", "", player.name));
    const meta = node("p", "athlete-meta");
    [player.team || "Team unavailable", leagueLabel(player.sport), roleLabel(player.sport, player.role)].forEach((text) => add(meta, node("span", "", text)));
    add(header, meta);
    const strip = node("div", "measurement-strip");
    const measurement = (label, value, unit, note) => {
      const item = node("div", "measurement");
      const amount = node("div", "measurement-value", value);
      if (unit && value !== "—") add(amount, node("span", "measurement-unit", unit));
      add(item, node("span", "measurement-label", label), amount, node("span", "measurement-note", note));
      return item;
    };
    add(strip, measurement("Height", fmt(player.height_cm, 1), "cm", "Model input"), measurement("Weight", fmt(player.weight_kg, 1), "kg", "Model input"), measurement("Age in snapshot", finite(player.age) ? fmt(Math.floor(player.age)) : "—", "yr", "Not a learned input"));
    add(header, strip);
    return header;
  }

  function renderControls() {
    const controls = node("section", "target-controls");
    controls.setAttribute("aria-label", "Target sport and role");
    add(controls, add(node("div", "control-label-row"), node("span", "", "Compare this build in…"), node("span", "", "Target sport")));
    const tabs = node("div", "target-tabs");
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "Target sport");
    state.manifest.sports.forEach((sport) => {
      const tab = node("button", "target-tab", leagueLabel(sport.id));
      tab.type = "button";
      tab.id = `target-${sport.id}`;
      tab.dataset.sport = sport.id;
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", String(state.sport === sport.id));
      tab.setAttribute("aria-controls", "target-result");
      tab.tabIndex = state.sport === sport.id ? 0 : -1;
      tab.addEventListener("click", () => changeSport(sport.id));
      tab.addEventListener("keydown", (event) => {
        const ids = state.manifest.sports.map((item) => item.id);
        let next = ids.indexOf(sport.id);
        if (event.key === "ArrowRight") next = (next + 1) % ids.length;
        else if (event.key === "ArrowLeft") next = (next - 1 + ids.length) % ids.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = ids.length - 1;
        else return;
        event.preventDefault();
        changeSport(ids[next]);
        document.getElementById(`target-${ids[next]}`)?.focus();
      });
      add(tabs, tab);
    });
    add(controls, tabs);
    const roleControl = node("div", "role-control");
    const label = node("label", "", "Possession-winning role");
    label.htmlFor = "target-role";
    const select = node("select");
    select.id = "target-role";
    availableRoles(state.sport).forEach((role) => {
      const option = node("option", "", role.label || role.id);
      option.value = role.id;
      option.selected = role.id === state.role;
      add(select, option);
    });
    select.addEventListener("change", (event) => { state.role = event.target.value; renderPlayer(); $("#target-role")?.focus(); announceResult(); });
    add(controls, add(roleControl, label, select));
    let context = state.player.sport === state.sport ? `Native league · ${league(state.sport)?.season_label || state.manifest.snapshot?.label || "2025 snapshot"} reference` : `Cross-sport body comparison · same height and weight, different elite reference group. Not a sport-switching forecast.`;
    if (state.player.sport === state.sport && state.role !== state.player.role) context += ` · Exploring ${roleLabel(state.sport, state.role)}, not this athlete’s recorded ${roleLabel(state.sport, state.player.role)} role.`;
    add(controls, node("p", "target-context", context));
    if (state.player.sport === state.sport && !availableRoles(state.sport).some((role) => role.id === state.player.role)) add(controls, node("p", "result-warning", `The recorded ${roleLabel(state.sport, state.player.role)} role has no fitted model. You are exploring a different role’s body reference, not this athlete’s native-role efficacy.`));
    return controls;
  }

  function changeSport(sport) {
    state.sport = sport;
    state.role = selectDefaultRole(sport);
    renderPlayer();
    updateUrl();
    announceResult();
  }

  function announceResult() {
    const result = selectedResult();
    const status = effectiveStatus(result, headFor(result));
    announce(`${leagueLabel(state.sport)}, ${roleLabel(state.sport, state.role)}. ${status === "provisional" ? `Provisional efficacy ${fmt(result.efficacy_rating, 1)} out of 100.` : (statusCopy[status]?.[0] || "Rating withheld.")}`);
  }

  function renderRating(result, head, status) {
    const grid = node("div", "rating-grid");
    const card = node("section", "rating-card");
    card.setAttribute("aria-label", "Efficacy estimate");
    const supported = status === "provisional" && finite(result?.efficacy_rating);
    add(card, add(node("div", "result-heading"), node("h3", "", "Efficacy estimate"), node("span", `badge${supported ? "" : " badge-neutral"}`, supported ? "Provisional" : "Withheld")));
    const score = node("div", "rating-number", supported ? fmt(result.efficacy_rating, 1) : "—");
    if (supported) add(score, node("span", "", "/ 100"));
    add(card, score);
    if (supported) add(card, node("p", "score-description", "Expected role-relative possession / disruption activity percentile."));
    else add(card, node("p", "withheld-title", statusCopy[status]?.[0] || "Rating withheld"), node("p", "score-description", "No supported numeric rating for this profile and role. This is not a score of zero."));
    const interval = result?.interval;
    if (supported && Array.isArray(interval) && interval.length === 2 && interval.every(finite)) {
      const range = node("div", "interval");
      add(range, add(node("div", "interval-label"), node("span", "", "Nominal 90% prediction interval"), node("strong", "", `${fmt(interval[0], 1)}–${fmt(interval[1], 1)}`)));
      const track = node("div", "interval-track");
      track.setAttribute("role", "img");
      track.setAttribute("aria-label", `Nominal 90 percent prediction interval from ${fmt(interval[0], 1)} to ${fmt(interval[1], 1)}. Coverage is not guaranteed.`);
      const band = node("span", "interval-band");
      band.style.left = `${Math.max(0, Math.min(100, interval[0]))}%`;
      band.style.width = `${Math.max(0, Math.min(100, interval[1]) - Math.max(0, interval[0]))}%`;
      const point = node("span", "interval-point");
      point.style.left = `${Math.max(0, Math.min(100, result.efficacy_rating))}%`;
      add(range, add(track, band, point), add(node("div", "axis-labels"), node("span", "", "0"), node("span", "", "100")));
      add(card, range);
    }
    const fit = node("section", "body-fit");
    fit.setAttribute("aria-label", "Body centrality, separate from efficacy");
    add(fit, node("h3", "result-heading", "Body fit"));
    const fitValue = node("div", "fit-value", fmt(result?.physical_fit, 0));
    if (finite(result?.physical_fit)) add(fitValue, node("span", "", "/ 100"));
    add(fit, fitValue);
    const blocks = node("div", "fit-track");
    blocks.setAttribute("aria-hidden", "true");
    for (let index = 0; index < 12; index += 1) add(blocks, node("i", finite(result?.physical_fit) && index < Math.round(result.physical_fit / 100 * 12) ? "filled" : ""));
    add(fit, blocks, node("p", "", "Body centrality within this role’s height-and-weight reference. Higher means more central, not more capable. It is not a probability or part of the efficacy score."));
    return add(grid, card, fit);
  }

  function renderExplanation(result, head, status) {
    const section = node("section", "result-section");
    add(section, node("h3", "", "Why this estimate"));
    let explanations = Array.isArray(result?.explanation) ? result.explanation.filter((text) => typeof text === "string" && text.trim()) : [];
    if (status !== "provisional") explanations = [statusCopy[status]?.[1] || "The evidence does not support displaying a rating for this profile.", ...explanations];
    const sourceFeature = finite(state.player.height_cm) && finite(state.player.weight_kg) ? `This comparison uses ${fmt(state.player.height_cm, 1)} cm and ${fmt(state.player.weight_kg, 1)} kg only. Age and observed season events are not learned inputs.` : "Both usable height and weight are required. Age and observed season events do not enter the prediction.";
    explanations = explanations.map((text) => /only.*height.*weight/i.test(text) ? sourceFeature : text);
    if (!explanations.some((text) => text === sourceFeature)) explanations.push(sourceFeature);
    if (!explanations.some((text) => /probability|transfer|skill/i.test(text))) explanations.push("The comparison describes an association among elite role peers, not individual skill, overall defensive quality or a probability of success in another sport.");
    const reasons = node("ol", "explanation-list");
    [...new Set(explanations)].slice(0, 3).forEach((text) => add(reasons, node("li", "", text)));
    return add(section, reasons);
  }

  function renderReference(result, head) {
    const section = node("section", "result-section two-col-details");
    const reference = node("div");
    add(reference, node("h3", "", "Closest reference build"));
    const archetype = result?.nearest_archetype;
    if (archetype && finite(archetype.height_cm) && finite(archetype.weight_kg)) {
      const values = node("div", "reference-measures");
      add(values, add(node("span", "", fmt(archetype.height_cm, 1)), node("span", "", "cm")), add(node("span", "", fmt(archetype.weight_kg, 1)), node("span", "", "kg")));
      add(reference, values);
      const captions = ["Nearest learned body-archetype center; not a comparison with a specific player."];
      if (finite(archetype.mean_target) && !isReview(result, head)) captions.push(`Shrunk training-cluster target mean: ${fmt(archetype.mean_target, 1)} / 100; not the ensemble prediction.`);
      if (isReview(result, head)) captions.push("Cluster activity-target mean is omitted while the defender target data are under review.");
      if (finite(archetype.membership)) captions.push(`Archetype membership: ${percent(archetype.membership, 0)}; not a success probability.`);
      add(reference, node("p", "reference-caption", captions.join(" ")));
    } else add(reference, node("p", "reference-caption", "No fitted physical archetype is available for this role/profile."));
    const blend = node("div");
    if (["missing_measurements", "unsupported_profile", "insufficient_support"].includes(effectiveStatus(result, head))) {
      add(blend, node("h3", "", "Model computation"), node("p", "reference-caption", "No personalized inference was performed for this profile and role. Reference-role model weights are not a prediction for this athlete."));
      return add(section, reference, blend);
    }
    add(blend, node("h3", "", "How the estimate is combined"));
    // Selected baseline is the deployed predictor, regardless of candidate blend diagnostics.
    const weights = head.selected_method === "baseline" ? { baseline50: 1 } : head.active_weights || {};
    const active = Object.entries(weights).filter(([, value]) => finite(value) && value > 0.0005).sort((a, b) => b[1] - a[1]);
    const experts = node("div", "expert-list");
    active.forEach(([key, weight]) => {
      const row = node("div", "expert-row");
      add(row, node("span", "expert-name", expertNames[key] || safeWords(key)), node("span", "expert-weight", percent(weight, 0)));
      const fill = node("span");
      fill.style.width = `${Math.min(100, Math.max(0, weight * 100))}%`;
      add(row, add(node("div", "expert-bar"), fill));
      add(experts, row);
    });
    add(blend, active.length ? experts : node("p", "reference-caption", "No active fitted model for this role."));
    add(blend, node("p", "fine-print", "Model weights describe the active blend, not causal effects or feature importance. All components use height and weight only."));
    return add(section, reference, blend);
  }

  function renderEvidence(result, head, status) {
    const details = node("details", "evidence-details");
    add(details, node("summary", "", "Training, test evidence & uncertainty"));
    const content = node("div", "evidence-content");
    const counts = node("div", "evidence-counts");
    [[head.train_athletes, "Training athletes"], [head.calibration_athletes, "Calibration"], [head.test_athletes, "Held-out test"]].forEach(([value, label]) => add(counts, add(node("div"), node("strong", "", fmt(value)), node("span", "", label))));
    add(content, counts);
    const metrics = head.metrics || {};
    const bootstrap = head.bootstrap || head.mse_improvement_cluster_bootstrap || {};
    const table = node("table", "evidence-table");
    const caption = node("caption", "sr-only", "Held-out model performance and uncertainty");
    const body = node("tbody");
    const rows = [
      ["Active method", head.selected_method === "baseline" ? "Constant midpoint (50)" : head.selected_method === "stack" ? "Weighted model ensemble" : "Not fitted"],
      ["Test mean absolute error", finite(metrics.mae) ? `${fmt(metrics.mae, 1)} points` : "—"],
      ["Midpoint baseline error", finite(metrics.baseline_mae) ? `${fmt(metrics.baseline_mae, 1)} points` : "—"],
      ["Test rank correlation", fmt(metrics.spearman, 2)],
      ["Test MSE improvement vs baseline", percent(metrics.relative_mse_improvement)],
      ["Bootstrap 95% improvement interval", finite(bootstrap.lower95) && finite(bootstrap.upper95) ? `${percent(bootstrap.lower95)} to ${percent(bootstrap.upper95)}` : "—"],
      ["Observed coverage of nominal 90% interval", percent(metrics.interval_90_empirical_coverage)],
      ["Statistically established improvement", head.improvement_statistically_established === true ? "Yes" : "No"],
    ];
    rows.forEach(([label, value]) => {
      const th = node("th", "", label);
      th.scope = "row";
      add(body, add(node("tr"), th, node("td", "", value)));
    });
    add(content, add(table, caption, body));
    const domains = head.target_domains || {};
    const domainEntries = Object.entries(domains).filter(([, domain]) => domain && typeof domain === "object");
    if (domainEntries.length) add(content, node("p", "evidence-message", `Role target domains: ${domainEntries.map(([key, domain]) => `${safeWords(key)}${finite(domain.weight) ? ` (${percent(domain.weight, 0)})` : ""}`).join("; ")}. Event rates are combined and ranked within the sport, role and season; the displayed estimate is not an event total.`));
    const nested = head.nested_cv || {};
    if (finite(nested.mae)) add(content, node("p", "evidence-message", `Model selection used grouped nested cross-validation on training athletes (MAE ${fmt(nested.mae, 1)} points). Final evaluation uses a separate latest-season held-out athlete group, not a future-season forecasting test.`));
    add(content, node("p", "evidence-message", "The nominal 90% interval is calibrated on a separate reference group. Its coverage is not guaranteed under season drift, out-of-domain physiques or cross-sport application. Small test samples make these estimates uncertain."));
    const limitations = [head.interval_diagnostic, ...(Array.isArray(head.limitations) ? head.limitations : []), ...(Array.isArray(result?.warnings) ? result.warnings : [])].filter((text) => typeof text === "string");
    [...new Set(limitations)].forEach((text) => add(content, node("p", "evidence-message", text)));
    const experimental = finite(result?.exploratory_estimate) ? result.exploratory_estimate : null;
    if (status !== "provisional" && finite(experimental)) {
      add(content, add(node("p", "experimental-score"), node("strong", "", `Non-validated exploratory estimate: ${fmt(experimental, 1)} / 100. `), node("span", "", "Shown for model inspection only. It is not a supported efficacy rating and should not be used to rank this athlete.")));
    }
    const partition = state.detail?.model_partition;
    const partitionLabel = typeof partition === "string" ? safeWords(partition) : partition && typeof partition === "object" ? safeWords(partition.partition || partition.split || partition.status || "not recorded") : "not recorded";
    add(content, node("p", "partition-note", `${state.detail?.included_in_training === true ? "This athlete contributed eligible training data to at least one fitted role/season in their source league. This does not establish inclusion in this particular target-role head, and their profile is not a fully unseen-athlete demonstration." : state.detail?.included_in_training === false ? "This athlete is not marked as included in any eligible fitted training head/season in their source league." : "Training membership is not recorded for this athlete."} Athlete-level partition: ${partitionLabel}.`));
    return add(details, content);
  }

  function renderObserved() {
    const observed = state.detail?.observed || {};
    const section = node("section", "result-section");
    add(section, add(node("div", "observed-header"), node("h3", "", "Season context · native league"), node("span", "", "Not prediction inputs")));
    const metrics = Array.isArray(observed.metrics) ? observed.metrics.filter((metric) => metric.value !== null && metric.value !== undefined).slice(0, 6) : [];
    if (metrics.length) {
      const grid = node("div", "observed-grid");
      metrics.forEach((metric) => {
        const value = finite(metric.value) ? fmt(metric.value, Number.isInteger(metric.value) ? 0 : 1) : String(metric.value);
        add(grid, add(node("div", "observed-metric"), node("strong", "", value + (metric.unit && metric.unit !== "count" ? ` ${metric.unit}` : "")), node("span", "", metric.label || safeWords(metric.key))));
      });
      add(section, grid);
    } else add(section, node("p", "observed-note", "No complete selected possession-event context is available for this player in this source snapshot."));
    if (finite(observed.opportunity)) add(section, node("p", "observed-note", `Recorded opportunity: ${fmt(observed.opportunity, Number.isInteger(observed.opportunity) ? 0 : 1)} ${observed.opportunity_unit || "units"}. Counts depend on playing time and sport-specific definitions.`));
    (observed.quality_notes || []).filter((text) => typeof text === "string").forEach((text) => add(section, node("p", "observed-note", text)));
    add(section, node("p", "observed-note", "These observed statistics help describe the player’s recorded season. They do not enter the height-and-weight efficacy prediction, and raw counts are not comparable across sports."));
    return section;
  }

  function renderPlayer() {
    const result = selectedResult();
    const head = headFor(result);
    const status = effectiveStatus(result, head);
    const body = node("div", "results-body");
    body.id = "target-result";
    body.setAttribute("role", "tabpanel");
    body.setAttribute("aria-labelledby", `target-${state.sport}`);
    add(body, renderRating(result, head, status));
    if (status !== "provisional") add(body, node("p", "result-warning", statusCopy[status]?.[1] || "A supported rating is not available for this profile and role."));
    else if (result?.warnings?.length || finite(head.metrics?.interval_90_empirical_coverage) && head.metrics.interval_90_empirical_coverage < 0.8) add(body, node("p", "result-warning", "Treat this estimate as exploratory. No role model currently has a statistically established improvement over the midpoint baseline; uncertainty and test evidence matter more than small score differences."));
    add(body, renderExplanation(result, head, status), renderReference(result, head), renderEvidence(result, head, status), renderObserved());
    panel.replaceChildren(renderHeader(), renderControls(), body);
    panel.setAttribute("aria-busy", "false");
  }

  function renderOverview() {
    const manifest = state.manifest;
    const heads = Object.values(manifest.heads || {});
    $("#snapshot-label").textContent = manifest.snapshot?.label || "2025 / 2025–26 snapshot";
    $("#fit-heads").textContent = heads.filter((head) => head.selected_method === "stack" || head.selected_method === "baseline").length;
    $("#point-checks").textContent = heads.filter((head) => head.status === "evidence_supported" || head.status === "provisional").length;
    $("#confirmed-heads").textContent = heads.filter((head) => head.improvement_statistically_established === true).length;
    const model = manifest.model || {};
    const trained = model.trained_at ? String(model.trained_at).slice(0, 10) : "not recorded";
    const generated = manifest.generated_at ? String(manifest.generated_at).slice(0, 10) : "not recorded";
    $("#model-provenance").textContent = `Model ${model.version || "version not recorded"} · trained ${trained} · local export ${generated}. Sources cover 2025 NFL and 2025–26 NBA, NHL and Premier League; this is not a live 2026–27 roster. The source-player pool is not an all-rostered census: NFL defenders, NBA source records, NHL skaters and Premier League source records. Some source players have no modeled native role. All predictions remain provisional research outputs.`;
    if (Array.isArray(manifest.sources) && manifest.sources.length) {
      const sources = node("details", "evidence-details source-details");
      add(sources, node("summary", "", "Data sources & coverage"));
      const content = node("div", "evidence-content");
      manifest.sources.forEach((source) => {
        const item = node("p", "evidence-message");
        const link = node("a", "source-link", source.label || source.id);
        try {
          const url = new URL(source.url);
          if (url.protocol === "https:") { link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer"; }
        } catch (_) { /* Invalid source links remain readable labels. */ }
        add(item, link, source.note ? node("span", "", ` — ${source.note}`) : null);
        add(content, item);
      });
      $("#model-sources").replaceChildren(add(sources, content));
      const moneyPuck = manifest.sources.find((source) => source.id === "moneypuck");
      if (moneyPuck) {
        const credit = node("p", "source-credit", "NHL event data: ");
        const link = node("a", "source-link", "MoneyPuck");
        link.href = "https://moneypuck.com/data.htm";
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        add(credit, link, node("span", "", ". Source access does not imply unrestricted reuse; see the source-specific terms above."));
        add($("#model-sources"), credit);
      }
    }
  }

  async function start() {
    $("#app-error").hidden = true;
    try {
      const manifest = await fetchJson("data/manifest.json");
      if (manifest.schema_version !== 1 || !Array.isArray(manifest.players) || !Array.isArray(manifest.sports)) throw new Error("Unsupported data-export format.");
      state.manifest = manifest;
      state.players = [...manifest.players].sort((a, b) => a.name.localeCompare(b.name));
      const select = $("#source-league");
      manifest.sports.forEach((sport) => {
        const option = node("option", "", leagueLabel(sport.id));
        option.value = sport.id;
        add(select, option);
      });
      renderOverview();
      const parameters = new URLSearchParams(window.location.search);
      const player = state.players.find((item) => item.id === parameters.get("player")) || state.players.find((item) => item.id === manifest.defaults?.player_id) || state.players[0];
      renderList();
      $("#explorer-layout").setAttribute("aria-busy", "false");
      if (!player) {
        panel.replaceChildren(add(node("div", "panel-error"), node("h2", "", "No player results exported yet"), node("p", "", "Build the local player export to populate this explorer.")));
        panel.setAttribute("aria-busy", "false");
        return;
      }
      await selectPlayer(player, parameters.get("sport"));
      const selectedButton = [...list.querySelectorAll("button")].find((button) => button.dataset.playerId === player.id);
      if (selectedButton) list.scrollTop = Math.max(0, selectedButton.offsetTop - list.offsetTop - 60);
    } catch (error) {
      const box = $("#app-error");
      box.replaceChildren(node("p", "", "The local research data could not be loaded. Check that this page is being served with its exported data folder, then try again."));
      const retry = node("button", "", "Reload data");
      retry.type = "button";
      retry.addEventListener("click", () => window.location.reload());
      add(box, retry);
      box.hidden = false;
      list.replaceChildren(node("p", "list-message", "Player data unavailable."));
      panel.replaceChildren(add(node("div", "panel-error"), node("h2", "", "Research snapshot unavailable"), node("p", "", "No ratings are shown without the saved model results.")));
      panel.setAttribute("aria-busy", "false");
      $("#explorer-layout").setAttribute("aria-busy", "false");
      announce("The local research data could not be loaded.");
    }
  }

  $("#player-search").addEventListener("input", (event) => { state.search = event.target.value; renderList(); });
  $("#source-league").addEventListener("change", (event) => { state.source = event.target.value; renderList(); announce(`${state.filtered.length} athletes in the current source-league search.`); });
  $("#player-search").addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") { event.preventDefault(); list.querySelector("button")?.focus(); }
    if (event.key === "Escape") { state.search = ""; event.target.value = ""; renderList(); }
  });
  list.addEventListener("keydown", (event) => {
    const buttons = [...list.querySelectorAll("button")];
    const position = buttons.indexOf(document.activeElement);
    if (position < 0) return;
    let next;
    if (event.key === "ArrowDown") next = Math.min(position + 1, buttons.length - 1);
    else if (event.key === "ArrowUp") next = Math.max(position - 1, 0);
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = buttons.length - 1;
    else return;
    event.preventDefault();
    buttons[next]?.focus();
  });
  start();
})();
