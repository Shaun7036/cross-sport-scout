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
    if (value >= 90) return "Top-tier model comparison";
    if (value >= 75) return "Strong model comparison";
    if (value >= 60) return "Above-average comparison";
    if (value >= 40) return "Around the middle";
    if (value >= 25) return "Below-average comparison";
    return "Lower comparison";
  }

  function bodyBand(value) {
    if (!finite(value)) return "Unavailable";
    if (value >= 75) return "Very typical target-role build";
    if (value >= 50) return "Fairly typical target-role build";
    if (value >= 25) return "Unusual target-role build";
    return "Rare target-role build";
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
      throw new Error("The requested file is outside the static site data directory.");
    }
    const response = await fetch(url, { credentials: "same-origin" });
    if (!response.ok) throw new Error(`The saved result could not be read (${response.status}).`);
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

  function metric(label, value, suffix = "") {
    const item = el("div", "metric-mini");
    append(item, el("span", "", label), el("strong", "", finite(value) ? `${number(value)}${suffix}` : "—"));
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
      const direction = item.contribution >= 0 ? "raised" : "lowered";
      list.append(
        el(
          "li",
          "",
          `${featureLabel(item.feature)} ${direction} the estimate in this fitted model (${item.contribution >= 0 ? "+" : ""}${number(item.contribution, 1)}).`,
        ),
      );
    });
    return list;
  }

  function scoreCard(
    title,
    estimate,
    { primary = false, bodyFit = false, fallback = "This result was withheld." } = {},
  ) {
    const card = el("article", `score-card${primary ? " primary" : ""}`);
    card.append(el("h4", "", title));
    if (!finite(estimate?.value)) {
      append(card, el("p", "score-value", "—"), el("p", "score-note", estimate?.evidence_warning || fallback));
      return card;
    }
    const value = el("div", "score-value", number(estimate.value, 1));
    value.append(el("small", "", bodyFit ? "build centrality" : "percentile-style score"));
    append(card, value, el("p", "score-band", bodyFit ? bodyBand(estimate.value) : band(estimate.value)));
    const range = estimate.range;
    if (finite(range?.lower) && finite(range?.upper)) {
      const coverage = finite(range.frozen_empirical_coverage)
        ? ` · ${number(range.frozen_empirical_coverage * 100, 0)}% frozen coverage`
        : "";
      card.append(el("p", "score-range", `Range: ${number(range.lower, 1)}–${number(range.upper, 1)}${coverage}`));
    }
    card.append(
      el(
        "p",
        "score-note",
        estimate.evidence_warning || "The estimate is shown with the evidence label saved by the frozen model.",
      ),
    );
    const contributions = contributionList(estimate);
    if (contributions) card.append(contributions);
    return card;
  }

  function nativeSection(detail) {
    const section = el("section", "panel analysis-section");
    const heading = el("div", "step-heading");
    append(
      heading,
      el("span", "step-number", "1"),
      append(
        el("div"),
        el("h3", "", "What the player has already shown"),
        el("p", "", "The observed score is descriptive: it compares this completed season with peers in the same sport and broad role."),
      ),
    );
    const observed = detail.native?.observed || {};
    const grid = el("div", "score-grid");
    const observedCard = scoreCard("Observed home-role standing", observed, {
      primary: true,
      fallback: "This season did not have enough evidence for an observed role score.",
    });
    const metrics = el("div", "metric-mini-grid");
    append(
      metrics,
      metric("Availability", observed.availability_percentile),
      metric("Three-year form", observed.sustained_3y_percentile),
      metric("Reference athletes", observed.reference_athletes),
    );
    observedCard.append(metrics);
    const profileCard = el("article", "score-card");
    profileCard.append(el("h4", "", "Playing-profile dimensions"));
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
    profileCard.append(domains.length ? list : el("p", "score-note", "No eligible playing profile was available."));
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
        el("h3", "", "What the models estimate for the next season"),
        el("p", "", "These are forward estimates from prior information. Their ranges and warnings are part of the answer."),
      ),
    );
    const grid = el("div", "score-grid");
    append(
      grid,
      scoreCard("Full native forecast", detail.native?.forecast),
      scoreCard("Build + playing-profile forecast", detail.native?.build_profile_forecast),
    );
    append(section, heading, grid);
    return section;
  }

  function targetOptions(detail) {
    return Object.entries(detail.targets || {}).filter(([, value]) => Object.keys(value.roles || {}).length);
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
        el("h3", "", "What might resemble another role"),
        el("p", "", "Choose a target role and keep body fit separate from the performance analogy."),
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
    basis.append(el("legend", "", "Comparison basis"));
    const choices = el("div", "basis-options");
    [
      ["physical", "Build only", "Listed height, weight and age"],
      ["transfer", "Build + playing profile", "Shared performance themes"],
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
      el("p", "comparison-note", "Body fit describes how typical the listed build is. It is never a measure of skill."),
    );

    const selectedRole = detail.targets?.[state.targetSport]?.roles?.[state.targetRole] || {};
    const estimate = state.basis === "transfer" ? selectedRole.transfer : selectedRole.physical;
    const scores = el("div", "score-grid");
    append(
      scores,
      scoreCard(
        state.basis === "transfer" ? "Transfer analogy" : "Physical association",
        estimate,
        { fallback: "The saved model withheld this comparison because the required evidence was unavailable." },
      ),
      scoreCard("Body fit", selectedRole.body_fit, {
        bodyFit: true,
        fallback: "Height or weight was missing, or the target role had too few comparable athletes.",
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
      playerList.append(el("p", "empty-state", "No featured athlete matches those filters."));
      return;
    }
    players.forEach((player) => {
      const button = el("button", "player-option");
      button.type = "button";
      button.setAttribute("aria-current", String(player.id === state.selected?.id));
      const copy = el("span", "player-copy");
      append(copy, el("strong", "", player.name), el("small", "", `${player.sport_label} · ${player.team || roleLabel(player.sport, player.role)}`));
      append(button, el("span", "avatar", initials(player.name)), copy);
      button.addEventListener("click", () => selectPlayer(player));
      playerList.append(button);
    });
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
          el("strong", "", "This profile could not be loaded."),
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
    result.replaceChildren(el("div", "result-error panel", "The saved portfolio data could not be read."));
  }

  async function initialise() {
    search.addEventListener("input", () => {
      state.query = search.value;
      renderPlayerList();
    });
    sourceSport.addEventListener("change", () => {
      state.sourceSport = sourceSport.value;
      renderPlayerList();
    });
    try {
      state.manifest = await fetchJson("manifest.json");
      state.metadata = await fetchJson(state.manifest.model_metadata_path || "model-metadata.json");
      state.players = Array.isArray(state.manifest.players) ? state.manifest.players : [];
      populateSourceSports();
      snapshotNote.textContent = `${number(state.players.length)} curated athletes · frozen model snapshot · all results precomputed`;
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

