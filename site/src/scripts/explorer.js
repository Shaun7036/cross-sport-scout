"use strict";

(() => {
  const dataRoot = new URL("../data/", document.baseURI);
  const state = {
    manifest: null,
    metadata: null,
    players: [],
    selected: null,
    detail: null,
    sourceSport: "all",
    query: "",
    targetSport: null,
    targetRole: null,
    basis: "physical",
    visiblePlayerLimit: 100,
    request: 0,
  };

  const search = document.querySelector("#player-search");
  const sourceSport = document.querySelector("#source-sport");
  const playerCount = document.querySelector("#player-count");
  const playerList = document.querySelector("#player-list");
  const result = document.querySelector("#result");
  const announcement = document.querySelector("#announcement");
  const appError = document.querySelector("#app-error");
  const explorerGrid = document.querySelector("#explorer-grid");
  const snapshotNote = document.querySelector("#snapshot-note");

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function append(parent, ...children) {
    children.filter(Boolean).forEach((child) => parent.append(child));
    return parent;
  }

  function finite(value) {
    return typeof value === "number" && Number.isFinite(value);
  }

  function number(value, digits = 0) {
    return finite(value)
      ? value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })
      : "—";
  }

  function words(value) {
    return String(value || "")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function initials(name) {
    return String(name || "?")
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0])
      .join("")
      .toUpperCase();
  }

  function band(value) {
    if (!finite(value)) return "Unavailable";
    if (value >= 90) return "Among the strongest matches";
    if (value >= 75) return "Strong match";
    if (value >= 60) return "Above-average match";
    if (value >= 40) return "Near the middle";
    if (value >= 25) return "Below-average match";
    return "Low match";
  }

  function bodyBand(value) {
    if (!finite(value)) return "Unavailable";
    if (value >= 75) return "Very common build for this role";
    if (value >= 50) return "Fairly common build for this role";
    if (value >= 25) return "Unusual build for this role";
    return "Rare build for this role";
  }

  function featureLabel(key) {
    return state.metadata?.feature_labels?.[key] || words(key);
  }

  function formatHeight(cm) {
    if (!finite(cm)) return "Not listed";
    const inches = Math.round(cm / 2.54);
    return `${Math.floor(inches / 12)}′${inches % 12}″ · ${number(cm)} cm`;
  }

  function formatWeight(kg) {
    if (!finite(kg)) return "Not listed";
    return `${number(kg * 2.20462)} lb · ${number(kg)} kg`;
  }

  async function fetchJson(path) {
    const relative = String(path || "").replace(/^data\//, "");
    const url = new URL(relative, dataRoot);
    if (url.origin !== window.location.origin || !url.pathname.startsWith(dataRoot.pathname)) {
      throw new Error("That saved profile is not available on this site.");
    }
    const response = await fetch(url, { credentials: "same-origin" });
    if (!response.ok) throw new Error(`The saved profile could not be opened (${response.status}).`);
    return response.json();
  }

  function sportConfig(sport) {
    return state.manifest?.sports?.find((item) => item.id === sport);
  }

  function sportLabel(sport) {
    return sportConfig(sport)?.label || String(sport || "").toUpperCase();
  }

  function roleLabel(sport, role) {
    return sportConfig(sport)?.roles?.find((item) => item.id === role)?.label || words(role);
  }

  function metric(label, value, suffix = "", digits = 0) {
    const item = el("div", "metric-mini");
    append(item, el("span", "", label), el("strong", "", finite(value) ? `${number(value, digits)}${suffix}` : "—"));
    return item;
  }

  function summaryCard(detail) {
    const player = detail.player;
    const card = el("section", "panel player-summary");
    const top = el("div", "summary-top");
    const name = el("div", "summary-name");
    append(
      name,
      el("span", "avatar", initials(player.name)),
      append(el("div"), el("p", "eyebrow", `${player.season} season`), el("h2", "", player.name)),
    );
    append(top, name, el("span", "league-label", player.sport_label || sportLabel(player.sport)));
    const meta = el("p", "summary-meta");
    [player.team, roleLabel(player.sport, player.role), player.position]
      .filter(Boolean)
      .forEach((value) => meta.append(el("span", "", value)));
    const measurements = el("dl", "measurements");
    [
      ["Height", formatHeight(player.height_cm)],
      ["Weight", formatWeight(player.weight_kg)],
      ["Age", finite(player.age) ? number(player.age) : "Not listed"],
    ].forEach(([label, value]) => {
      const item = el("div");
      append(item, el("dt", "", label), el("dd", "", value));
      measurements.append(item);
    });
    append(card, top, meta, measurements);
    return card;
  }

  function contributionList(estimate) {
    const contributions = (estimate?.top_contributions || []).filter((item) => finite(item.contribution));
    if (!contributions.length) return null;
    const list = el("ul", "contribution-list");
    contributions.slice(0, 4).forEach((item) => {
      const direction = item.contribution >= 0 ? "pushed this score higher" : "pushed this score lower";
      list.append(
        el(
          "li",
          "",
          `${featureLabel(item.feature)} ${direction} (${item.contribution >= 0 ? "+" : ""}${number(item.contribution, 1)}).`,
        ),
      );
    });
    return list;
  }

  function scoreCard(
    title,
    estimate,
    { primary = false, bodyFit = false, fallback = "This result was withheld.", note = null } = {},
  ) {
    const card = el("article", `score-card${primary ? " primary" : ""}`);
    card.append(el("h4", "", title));
    if (!finite(estimate?.value)) {
      append(card, el("p", "score-value", "—"), el("p", "score-note", estimate?.evidence_warning || fallback));
      return card;
    }
    const value = el("div", "score-value", number(estimate.value, 1));
    value.append(el("small", "", bodyFit ? "body match / 100" : "score out of 100"));
    append(card, value, el("p", "score-band", bodyFit ? bodyBand(estimate.value) : band(estimate.value)));
    const range = estimate.range;
    if (finite(range?.lower) && finite(range?.upper)) {
      const coverage = finite(range.frozen_empirical_coverage)
        ? ` · Similar past ranges contained ${number(range.frozen_empirical_coverage * 100, 0)}% of results`
        : "";
      card.append(el("p", "score-range", `Expected range: ${number(range.lower, 1)}–${number(range.upper, 1)}${coverage}`));
    }
    card.append(
      el(
        "p",
        "score-note",
        note || estimate.evidence_warning || "This is an estimate, not a guarantee.",
      ),
    );
    const contributions = contributionList(estimate);
    if (contributions) card.append(contributions);
    return card;
  }

  function validationEvidence(validation, kind) {
    const box = el("div", "validation-evidence");
    box.append(el("p", "validation-label", "How this model tested in 2025"));
    if (!validation || !finite(validation.mean_error) || !finite(validation.test_players)) {
      box.append(el("p", "validation-copy", "There was not enough held-out evidence to score this model check."));
      return box;
    }

    const change = validation.baseline_improvement_percent;
    const improved = finite(change) && change >= 0;
    const status = String(validation.status || "");
    const supported = kind === "profile"
      ? status === "supported"
      : status === "supported_over_history_baselines";
    const changeText = finite(change)
      ? `${number(Math.abs(change), 1)}% ${improved ? "lower" : "higher"} error`
      : "No benchmark comparison";
    const headline = el("div", `validation-result${supported ? " passed" : " limited"}`);
    append(
      headline,
      el("strong", "", changeText),
      el("span", "", `than ${validation.baseline_label || "the simple benchmark"}`),
    );
    box.append(headline);

    let explanation;
    if (kind === "profile" && status === "supported") {
      explanation = "Playing style added useful information beyond body build alone.";
    } else if (kind === "profile" && status === "not_supported") {
      explanation = "Playing style did not clearly improve on body build alone, so use this result cautiously.";
    } else if (kind === "native" && status === "supported_over_history_baselines") {
      explanation = "The model clearly improved on the simple history forecast.";
    } else if (kind === "native" && status === "history_baseline_preferred_or_insufficient") {
      explanation = "The model did not clearly beat a simple history forecast, so this outlook remains experimental.";
    } else {
      explanation = "This model check has limited evidence and should be treated as experimental.";
    }
    box.append(el("p", "validation-copy", explanation));

    const metrics = el("div", "validation-metrics");
    append(
      metrics,
      metric("Players tested", validation.test_players),
      metric("Average miss", validation.mean_error, " pts", 1),
      metric("Benchmark miss", validation.baseline_error, " pts", 1),
    );
    box.append(metrics);
    return box;
  }

  function nativeSection(detail) {
    const section = el("section", "panel analysis-section");
    const heading = el("div", "step-heading");
    append(
      heading,
      el("span", "step-number", "1"),
      append(
        el("div"),
        el("h3", "", "Current-sport performance"),
        el("p", "", "This completed-season score compares the player only with peers in the same sport and broad role."),
      ),
    );
    const observed = detail.native?.observed || {};
    const grid = el("div", "score-grid");
    const observedCard = scoreCard("Completed-season result", observed, {
      primary: true,
      fallback: "This season did not have enough information for a reliable score.",
      note: "This describes the completed season; it is not a prediction.",
    });
    const metrics = el("div", "metric-mini-grid");
    append(
      metrics,
      metric("Playing time", observed.availability_percentile),
      metric("Three-year form", observed.sustained_3y_percentile),
      metric("Players compared", observed.reference_athletes),
    );
    observedCard.append(metrics);
    const profileCard = el("article", "score-card");
    profileCard.append(el("h4", "", "Playing-style strengths"));
    const domains = (detail.profile?.domains || []).filter(
      (item) => finite(item.value) && item.key !== "domain_coverage_fraction",
    );
    const list = el("div", "domain-list");
    domains.slice(0, 7).forEach((item) => {
      const row = el("div", "domain-row");
      const track = el("span", "mini-track");
      const fill = el("i");
      fill.style.width = `${Math.max(0, Math.min(100, item.value))}%`;
      track.append(fill);
      append(row, el("span", "", item.label || words(item.key)), track, el("strong", "", number(item.value)));
      list.append(row);
    });
    profileCard.append(domains.length ? list : el("p", "score-note", "There was not enough information to show a playing-style profile."));
    append(grid, observedCard, profileCard);
    append(section, heading, grid);
    return section;
  }

  function forecastSection(detail) {
    const section = el("section", "panel analysis-section");
    const heading = el("div", "step-heading");
    append(
      heading,
      el("span", "step-number", "2"),
      append(
        el("div"),
        el("h3", "", "Next-season outlook and model check"),
        el("p", "", "These estimates use earlier seasons. Each card also shows how that role model performed on players held back from training."),
      ),
    );
    const grid = el("div", "score-grid");
    const roleKey = `${detail.player.sport}:${detail.player.role}`;
    const validation = state.metadata?.role_validation?.[roleKey] || {};
    const nativeCard = scoreCard("Overall outlook", detail.native?.forecast);
    nativeCard.append(validationEvidence(validation.native_forecast, "native"));
    const profileCard = scoreCard("Build + playing-style outlook", detail.native?.build_profile_forecast);
    profileCard.append(validationEvidence(validation.build_profile, "profile"));
    append(grid, nativeCard, profileCard);
    append(section, heading, grid);
    return section;
  }

  function targetOptions(detail) {
    return Object.entries(detail.targets || {}).filter(
      ([sport, value]) => sport !== detail.player.sport && Object.keys(value.roles || {}).length,
    );
  }

  function normaliseTarget(detail, preferred = {}) {
    const sports = targetOptions(detail);
    const requestedSport = preferred.sport || state.targetSport;
    state.targetSport = sports.some(([sport]) => sport === requestedSport)
      ? requestedSport
      : sports.find(([sport]) => sport !== detail.player.sport)?.[0] || sports[0]?.[0];
    const roles = detail.targets?.[state.targetSport]?.roles || {};
    const requestedRole = preferred.role || state.targetRole;
    state.targetRole = Object.hasOwn(roles, requestedRole) ? requestedRole : Object.keys(roles)[0];
    state.basis = ["physical", "transfer"].includes(preferred.basis) ? preferred.basis : state.basis;
  }

  function updateUrl() {
    if (!state.selected) return;
    const url = new URL(window.location.href);
    url.searchParams.set("player", state.selected.id);
    if (state.targetSport) url.searchParams.set("sport", state.targetSport);
    if (state.targetRole) url.searchParams.set("role", state.targetRole);
    url.searchParams.set("basis", state.basis);
    window.history.replaceState({}, "", url);
  }

  function comparisonSection(detail) {
    const section = el("section", "panel analysis-section");
    const heading = el("div", "step-heading");
    append(
      heading,
      el("span", "step-number", "3"),
      append(
        el("div"),
        el("h3", "", "Other-sport comparisons"),
        el("p", "", "Choose a different sport and role. The body match is kept separate from the playing-style comparison."),
      ),
    );
    const controls = el("div", "comparison-controls");
    const selects = el("div", "select-grid");
    const sportWrap = el("div");
    const sportSelect = el("select");
    sportSelect.id = "target-sport";
    targetOptions(detail).forEach(([sport]) => {
      const option = el("option", "", sportLabel(sport));
      option.value = sport;
      option.selected = sport === state.targetSport;
      sportSelect.append(option);
    });
    append(sportWrap, Object.assign(el("label", "", "Target sport"), { htmlFor: sportSelect.id }), sportSelect);
    const roleWrap = el("div");
    const roleSelect = el("select");
    roleSelect.id = "target-role";
    Object.entries(detail.targets?.[state.targetSport]?.roles || {}).forEach(([role, value]) => {
      const option = el("option", "", value.label || roleLabel(state.targetSport, role));
      option.value = role;
      option.selected = role === state.targetRole;
      roleSelect.append(option);
    });
    append(roleWrap, Object.assign(el("label", "", "Target role"), { htmlFor: roleSelect.id }), roleSelect);
    append(selects, sportWrap, roleWrap);

    const basis = el("fieldset", "basis");
    basis.append(el("legend", "", "What should be compared?"));
    const choices = el("div", "basis-options");
    [
      ["physical", "Build only", "Listed height, weight and age"],
      ["transfer", "Build + playing style", "Shared performance patterns"],
    ].forEach(([value, label, note]) => {
      const choice = el("label", "basis-option");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "basis";
      input.value = value;
      input.checked = state.basis === value;
      append(choice, input, el("strong", "", label), el("small", "", note));
      choices.append(choice);
    });
    basis.append(choices);
    append(
      controls,
      selects,
      basis,
      el("p", "comparison-note", "Body match only asks whether the listed height and weight are common for that role. It does not measure skill."),
    );

    const selectedRole = detail.targets?.[state.targetSport]?.roles?.[state.targetRole] || {};
    const estimate = state.basis === "transfer" ? selectedRole.transfer : selectedRole.physical;
    const scores = el("div", "score-grid");
    append(
      scores,
      scoreCard(
        state.basis === "transfer" ? "Overall role match" : "Build-based match",
        estimate,
        { fallback: "There was not enough information to show this comparison." },
      ),
      scoreCard("Body match", selectedRole.body_fit, {
        bodyFit: true,
        fallback: "Height or weight was missing, or too few comparable players were available.",
        note: "This compares body build only; it does not measure skill.",
      }),
    );

    sportSelect.addEventListener("change", () => {
      normaliseTarget(detail, { sport: sportSelect.value, basis: state.basis });
      updateUrl();
      renderResult();
    });
    roleSelect.addEventListener("change", () => {
      state.targetRole = roleSelect.value;
      updateUrl();
      renderResult();
    });
    choices.querySelectorAll("input").forEach((input) => {
      input.addEventListener("change", () => {
        state.basis = input.value;
        updateUrl();
        renderResult();
      });
    });
    append(section, heading, controls, scores);
    return section;
  }

  function renderResult() {
    if (!state.detail) return;
    result.replaceChildren(
      summaryCard(state.detail),
      nativeSection(state.detail),
      forecastSection(state.detail),
      comparisonSection(state.detail),
    );
    result.setAttribute("aria-busy", "false");
  }

  function filteredPlayers() {
    const query = state.query.trim().toLocaleLowerCase();
    return state.players.filter((player) => {
      if (state.sourceSport !== "all" && player.sport !== state.sourceSport) return false;
      if (!query) return true;
      return [player.name, player.team, player.position, player.role, player.sport_label]
        .filter(Boolean)
        .some((value) => String(value).toLocaleLowerCase().includes(query));
    });
  }

  function renderPlayerList() {
    const players = filteredPlayers();
    playerCount.textContent = number(players.length);
    playerList.replaceChildren();
    if (!players.length) {
      playerList.append(el("p", "empty-state", "No player matches those filters."));
      return;
    }
    players.slice(0, state.visiblePlayerLimit).forEach((player) => {
      const button = el("button", "player-option");
      button.type = "button";
      button.setAttribute("aria-current", String(player.id === state.selected?.id));
      const copy = el("span", "player-copy");
      append(copy, el("strong", "", player.name), el("small", "", `${player.sport_label} · ${player.team || roleLabel(player.sport, player.role)}`));
      append(button, el("span", "avatar", initials(player.name)), copy);
      button.addEventListener("click", () => selectPlayer(player));
      playerList.append(button);
    });
    if (players.length > state.visiblePlayerLimit) {
      const remaining = players.length - state.visiblePlayerLimit;
      const more = el("button", "load-more", `Show more players (${number(remaining)} remaining)`);
      more.type = "button";
      more.addEventListener("click", () => {
        state.visiblePlayerLimit += 100;
        renderPlayerList();
      });
      playerList.append(more);
    }
  }

  async function selectPlayer(player, preferred = {}) {
    const request = ++state.request;
    state.selected = player;
    renderPlayerList();
    result.setAttribute("aria-busy", "true");
    result.replaceChildren(append(el("div", "loading panel"), el("span"), el("p", "", "Loading saved results…")));
    try {
      const detail = await fetchJson(player.detail_path);
      if (request !== state.request) return;
      state.detail = detail;
      const hasPreferred = preferred.sport || preferred.role || preferred.basis;
      const featured = state.manifest?.featured_cases?.find((item) => item.player_id === player.id);
      normaliseTarget(
        detail,
        hasPreferred
          ? preferred
          : {
              sport: featured?.target_sport,
              role: featured?.target_role,
              basis: featured ? "transfer" : "physical",
            },
      );
      updateUrl();
      renderResult();
      renderPlayerList();
      announcement.textContent = `${player.name} profile loaded.`;
    } catch (error) {
      if (request !== state.request) return;
      result.replaceChildren(
        append(
          el("div", "result-error panel"),
          el("strong", "", "This player profile could not be opened."),
          el("p", "", error instanceof Error ? error.message : "Unknown error"),
        ),
      );
    }
  }

  function populateSourceSports() {
    (state.manifest?.sports || []).forEach((sport) => {
      const option = el("option", "", sport.label);
      option.value = sport.id;
      sourceSport.append(option);
    });
  }

  function showFatalError(message) {
    appError.hidden = false;
    appError.textContent = message;
    explorerGrid.setAttribute("aria-busy", "false");
    playerList.replaceChildren(el("p", "empty-state", "The player list could not be loaded."));
    result.replaceChildren(el("div", "result-error panel", "The saved player data could not be opened."));
  }

  async function loadPlayers() {
    const indexes = state.manifest?.player_indexes;
    if (!Array.isArray(indexes) || !indexes.length) {
      return Array.isArray(state.manifest?.players) ? state.manifest.players : [];
    }
    const groups = await Promise.all(indexes.map((index) => fetchJson(index.path)));
    return groups
      .flat()
      .filter((player) => player && player.id)
      .sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
  }

  async function initialise() {
    search.addEventListener("input", () => {
      state.query = search.value;
      state.visiblePlayerLimit = 100;
      renderPlayerList();
    });
    sourceSport.addEventListener("change", () => {
      state.sourceSport = sourceSport.value;
      state.visiblePlayerLimit = 100;
      renderPlayerList();
    });
    try {
      state.manifest = await fetchJson("manifest.json");
      state.metadata = await fetchJson(state.manifest.model_metadata_path || "model-metadata.json");
      state.players = await loadPlayers();
      populateSourceSports();
      snapshotNote.textContent = `${number(state.players.length)} players · saved 2025 results`;
      explorerGrid.setAttribute("aria-busy", "false");
      const params = new URLSearchParams(window.location.search);
      const requested = params.get("player");
      const defaultId = state.manifest.defaults?.player_id;
      const player = state.players.find((item) => item.id === requested)
        || state.players.find((item) => item.id === defaultId)
        || state.players[0];
      renderPlayerList();
      if (!player) throw new Error("The public player list is empty.");
      await selectPlayer(player, {
        sport: params.get("sport") || state.manifest.defaults?.target_sport,
        role: params.get("role") || state.manifest.defaults?.target_role,
        basis: params.get("basis") || "physical",
      });
    } catch (error) {
      showFatalError(error instanceof Error ? error.message : "The site data could not be loaded.");
    }
  }

  initialise();
})();

