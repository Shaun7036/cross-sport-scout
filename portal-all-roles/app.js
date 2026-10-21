/* Read-only viewer: inference and evidence gates run before this static export. */
"use strict";

(() => {
  const $ = (selector) => document.querySelector(selector);
  const state = {
    manifest: null,
    players: [],
    selected: null,
    detail: null,
    targetSport: null,
    sourceSport: "all",
    query: "",
    request: 0,
  };
  const cache = new Map();
  const result = $("#result");
  const playerList = $("#player-list");

  const statusText = {
    available: "Available",
    eligible: "Observed",
    low_sample: "Low sample",
    not_observed: "Not observed",
    not_applicable_without_source_performance: "Not applicable for the native sport",
    withheld_no_fitted_model: "Withheld · no fitted model",
    withheld_missing_height_or_weight: "Withheld · missing height or weight",
    withheld_missing_fixed_bridge_dimensions: "Withheld · missing mapped performance",
    withheld_missing_required_dimensions: "Withheld · missing mapped performance",
    withheld_proxy_model_failed_baseline_gate: "Withheld · proxy model failed its evidence gate",
    withheld_target_proxy_reconstruction_failed_gate: "Withheld · target proxy failed its reconstruction gate",
    withheld_source_performance_not_eligible: "Withheld · source season is not eligible",
    withheld_out_of_domain: "Withheld · outside the reference domain",
    unknown: "Evidence unavailable",
  };

  const scoreDefinitions = {
    observed: {
      number: "01",
      label: "Native observed",
      copy: "Retrospective standing among athletes in this player’s recorded role and season.",
    },
    forecast: {
      number: "02",
      label: "Native next-season forecast",
      copy: "A prospective role percentile built from earlier information; it may be withheld or trail a history baseline.",
    },
    physical: {
      number: "03",
      label: "Target-role physical-only estimate",
      copy: "An association between this body profile and observed outcomes in the selected target role.",
    },
    transfer: {
      number: "04",
      label: "Cross-sport transfer guesstimate",
      copy: "A build plus transferable-performance analogy. This is exploratory and not a probability of switching successfully.",
    },
  };

  function element(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined && text !== null) item.textContent = String(text);
    return item;
  }

  function append(parent, ...children) {
    children.filter(Boolean).forEach((child) => parent.append(child));
    return parent;
  }

  function finite(value) {
    return typeof value === "number" && Number.isFinite(value);
  }

  function format(value, digits = 0) {
    return finite(value)
      ? value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })
      : "—";
  }

  function words(value) {
    return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function searchable(value) {
    return String(value || "").normalize("NFD").replace(/\p{Diacritic}/gu, "").toLocaleLowerCase();
  }

  function sportRecord(id) {
    return state.manifest?.sports?.find((sport) => sport.id === id);
  }

  function sportLabel(id) {
    return sportRecord(id)?.label || String(id || "Unknown").toUpperCase();
  }

  function roleLabel(sport, role) {
    return sportRecord(sport)?.roles?.find((item) => item.id === role)?.label || words(role);
  }

  function initials(name) {
    return String(name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  }

  function announce(message) {
    $("#announcement").textContent = message;
  }

  async function fetchJson(path) {
    const url = new URL(path, document.baseURI);
    const dataRoot = new URL("data/", document.baseURI);
    if (url.origin !== window.location.origin || !url.pathname.startsWith(dataRoot.pathname)) {
      throw new Error("The requested export is outside this local portal.");
    }
    const response = await fetch(url, { cache: "no-store", credentials: "same-origin" });
    if (!response.ok) throw new Error(`The saved export could not be read (${response.status}).`);
    return response.json();
  }

  function renderPlayerList() {
    const needle = searchable(state.query.trim());
    const matches = state.players.filter((player) => {
      const inSport = state.sourceSport === "all" || player.sport === state.sourceSport;
      const inSearch = !needle || searchable(`${player.name} ${player.team || ""} ${player.role || ""}`).includes(needle);
      return inSport && inSearch;
    });
    $("#player-count").textContent = matches.length.toLocaleString("en-US");
    playerList.replaceChildren();
    if (!matches.length) {
      playerList.append(element("p", "empty-state", "No athletes match this search."));
      return;
    }
    let visible = matches.slice(0, 180);
    if (state.selected && matches.some((player) => player.id === state.selected.id) && !visible.some((player) => player.id === state.selected.id)) {
      visible = [state.selected, ...visible.slice(0, 179)];
    }
    const fragment = document.createDocumentFragment();
    visible.forEach((player) => {
      const button = element("button", "player-option");
      button.type = "button";
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", String(player.id === state.selected?.id));
      button.dataset.playerId = player.id;
      const avatar = element("span", "avatar", initials(player.name));
      avatar.setAttribute("aria-hidden", "true");
      const copy = element("span", "player-option-copy");
      append(
        copy,
        element("strong", "", player.name),
        element("small", "", `${player.team || "Team unavailable"} · ${sportLabel(player.sport)} · ${roleLabel(player.sport, player.role)}`),
      );
      append(button, avatar, copy);
      button.addEventListener("click", () => selectPlayer(player));
      fragment.append(button);
    });
    playerList.append(fragment);
    if (matches.length > visible.length) {
      playerList.append(element("p", "list-limit", `Showing the first ${visible.length}. Search to narrow ${matches.length.toLocaleString("en-US")} matches.`));
    }
  }

  function updatePlayerSelection() {
    let selectedIsVisible = false;
    playerList.querySelectorAll("[data-player-id]").forEach((button) => {
      button.setAttribute("aria-selected", String(button.dataset.playerId === state.selected?.id));
      selectedIsVisible ||= button.dataset.playerId === state.selected?.id;
    });
    if (state.selected && !selectedIsVisible) renderPlayerList();
  }

  function validTargetSport(preferred) {
    const available = Object.keys(state.detail?.targets || {});
    if (preferred && available.includes(preferred)) return preferred;
    if (state.selected?.sport && available.includes(state.selected.sport)) return state.selected.sport;
    return available[0] || state.manifest?.sports?.[0]?.id || null;
  }

  async function selectPlayer(player, preferredSport = state.targetSport) {
    const request = ++state.request;
    state.selected = player;
    state.detail = null;
    updatePlayerSelection();
    result.setAttribute("aria-busy", "true");
    const loading = element("div", "loading-state");
    append(loading, element("span"), element("p", "", `Loading ${player.name}…`));
    result.replaceChildren(loading);
    try {
      let detail = cache.get(player.id);
      if (!detail) {
        detail = await fetchJson(player.detail_path);
        cache.set(player.id, detail);
      }
      if (request !== state.request) return;
      state.detail = detail;
      state.targetSport = validTargetSport(preferredSport);
      renderResult();
      writeUrl();
      announce(`${player.name} selected. ${sportLabel(state.targetSport)} target roles are shown.`);
    } catch (error) {
      if (request !== state.request) return;
      const box = element("div", "result-error");
      append(box, element("h2", "", "This athlete could not be loaded"), element("p", "", "The saved player result is missing or unreadable."));
      const retry = element("button", "button", "Try again");
      retry.type = "button";
      retry.addEventListener("click", () => selectPlayer(player, preferredSport));
      append(box, retry);
      result.replaceChildren(box);
      result.setAttribute("aria-busy", "false");
      announce("The athlete result could not be loaded. A retry button is available.");
    }
  }

  function writeUrl() {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("player", state.selected.id);
      url.searchParams.set("sport", state.targetSport);
      window.history.replaceState(null, "", url);
    } catch (_) {
      /* History access is optional for embedded previews. */
    }
  }

  function scoreAvailable(score, observed = false) {
    if (!score || !finite(score.value)) return false;
    return observed ? score.status !== "not_observed" : score.status === "available";
  }

  function scoreStatus(score, observed = false) {
    if (scoreAvailable(score, observed)) {
      const support = {
        association_gate_supported: "Supported association",
        supported_over_neutral_and_history_baselines: "Supported vs neutral + history",
        experimental_unsupported: "Experimental · unsupported",
        experimental_target_proxy_passed_not_cross_sport_validated: "Exploratory proxy only",
      };
      return support[score?.support_status] || statusText[score.status] || "Available";
    }
    if (score?.status === "eligible") return "Withheld · observed value unavailable";
    return statusText[score?.status] || words(score?.status || "unknown");
  }

  function contributionList(score) {
    const section = element("div", "reasons");
    const contributions = Array.isArray(score?.top_contributions) ? score.top_contributions.slice(0, 5) : [];
    append(section, element("h5", "", "Top model contribution reasons"));
    if (!contributions.length) {
      append(section, element("p", "quiet small", "No model contribution breakdown is available for this result."));
      return section;
    }
    const list = element("ol");
    contributions.forEach((reason) => {
      const item = element("li");
      const value = finite(reason.contribution) ? `${reason.contribution >= 0 ? "+" : ""}${format(reason.contribution, 1)} pts` : "effect unavailable";
      append(item, element("span", "", words(reason.feature)), element("strong", "", value));
      if (reason.imputed) append(item, element("small", "", "Missing input was imputed by the fitted model."));
      list.append(item);
    });
    section.append(list);
    return section;
  }

  function evidenceNotes(score) {
    const notes = element("div", "evidence-notes");
    const items = [];
    if (score?.evidence_class) items.push(`Evidence: ${words(score.evidence_class)}`);
    if (score?.evaluation_status) items.push(`Evaluation: ${words(score.evaluation_status)}`);
    if (finite(score?.reference_rows)) items.push(`${format(score.reference_rows)} reference rows`);
    if (score?.ood?.status === "in_domain") items.push("Within the fitted feature domain");
    if (score?.ood?.status === "in_domain_with_age_warning") items.push("Within the fitted domain, with an age warning");
    if (score?.ood?.status === "out_of_domain" || score?.status === "withheld_out_of_domain") items.push("Outside the fitted feature domain");
    const outside = Array.isArray(score?.ood?.features)
      ? score.ood.features.filter((item) => item.status === "outside_1_99_reference").map((item) => words(item.feature))
      : [];
    if (outside.length) items.push(`Reference-range flags: ${outside.join(", ")}`);
    if (score?.forecast_support) items.push(`Forecast support: ${words(score.forecast_support)}`);
    if (score?.support_status) items.push(`Support: ${words(score.support_status)}`);
    if (score?.target_proxy_reconstruction_gate) items.push(`Target-proxy reconstruction gate: ${words(score.target_proxy_reconstruction_gate)}`);
    if (score?.semantic_bridge_grade) items.push(`Semantic bridge: ${words(score.semantic_bridge_grade)}`);
    if (Array.isArray(score?.dimensions) && score.dimensions.length) items.push(`Mapped dimensions: ${score.dimensions.map(words).join(", ")}`);
    items.forEach((item) => notes.append(element("span", "", item)));
    return notes;
  }

  function sensitivity(score) {
    const range = score?.analogy_sensitivity_range;
    if (!Array.isArray(range) || range.length !== 2 || !range.every(finite)) return null;
    const block = element("div", "sensitivity");
    append(
      block,
      element("span", "", "Model-error sensitivity range"),
      element("strong", "", `${format(range[0], 1)}–${format(range[1], 1)}`),
      element("small", "", score.range_warning || "This is not a calibrated confidence interval."),
    );
    return block;
  }

  function scoreCard(kind, score, options = {}) {
    const definition = scoreDefinitions[kind];
    const card = element("section", `score-card score-${kind}`);
    const heading = element("div", "score-heading");
    append(heading, element("span", "score-number", definition.number), element("h4", "", definition.label));
    card.append(heading);
    card.append(element("p", "score-copy", definition.copy));

    const available = scoreAvailable(score, options.observed);
    const readout = element("div", "score-readout");
    const number = element("div", "score-value", available ? format(score.value, 1) : "—");
    if (available) number.append(element("small", "", " percentile"));
    const experimental = String(score?.support_status || "").startsWith("experimental");
    const badgeClass = available ? (experimental ? "experimental" : "available") : "withheld";
    const badge = element("span", `status-badge ${badgeClass}`, scoreStatus(score, options.observed));
    append(readout, number, badge);
    card.append(readout);

    if (available) {
      const track = element("div", "score-track");
      track.setAttribute("role", "img");
      track.setAttribute("aria-label", `${definition.label}: ${format(score.value, 1)} percentile`);
      const fill = element("span");
      fill.style.width = `${Math.max(0, Math.min(100, score.value))}%`;
      track.append(fill);
      card.append(track);
    } else {
      card.append(element("p", "withheld-copy", score?.reason ? `Reason: ${words(score.reason)}` : "No numeric result is supported here. A withheld result is not a score of zero."));
    }

    if (score?.evidence_warning) card.append(element("p", "evidence-warning", score.evidence_warning));
    if (score?.saturation_warning) card.append(element("p", "evidence-warning saturation-warning", score.saturation_warning));

    const range = sensitivity(score);
    if (range) card.append(range);
    card.append(evidenceNotes(score));
    if (options.contributions) card.append(contributionList(score));
    return card;
  }

  function playerHeader() {
    const player = state.selected;
    const header = element("header", "athlete-header");
    const title = element("div", "athlete-title");
    append(title, element("span", "athlete-avatar", initials(player.name)), append(element("div"), element("p", "eyebrow", "Selected athlete"), element("h2", "", player.name)));
    const meta = element("p", "athlete-meta");
    [sportLabel(player.sport), roleLabel(player.sport, player.role), player.team || "Team unavailable", `Season ${player.season}`].forEach((item) => meta.append(element("span", "", item)));
    append(header, title, meta);
    const measurements = element("dl", "measurements");
    const values = [
      ["Height", finite(player.height_cm) ? `${format(player.height_cm, 1)} cm` : "Unavailable"],
      ["Weight", finite(player.weight_kg) ? `${format(player.weight_kg, 1)} kg` : "Unavailable"],
      ["Age", finite(player.age) ? format(player.age, 1) : "Unavailable"],
      [
        finite(player.opportunity) ? "Opportunity" : "Roster weeks",
        finite(player.opportunity)
          ? format(player.opportunity, 0)
          : finite(player.rostered_weeks)
            ? format(player.rostered_weeks, 0)
            : "Unavailable",
      ],
    ];
    values.forEach(([label, value]) => append(measurements, append(element("div"), element("dt", "", label), element("dd", "", value))));
    header.append(measurements);
    return header;
  }

  function observedComponents(score) {
    const entries = [
      ["Quality", score?.quality_percentile],
      ["Availability", score?.availability_percentile],
      ["Total impact", score?.total_impact_percentile],
      ["Sustained 3-year", score?.sustained_3y_percentile],
    ].filter(([, value]) => finite(value));
    if (!entries.length) return null;
    const block = element("div", "component-grid");
    entries.forEach(([label, value]) => append(block, append(element("div"), element("span", "", label), element("strong", "", format(value, 1)))));
    return block;
  }

  function nativeStrengths(profile) {
    const domains = Array.isArray(profile?.domains)
      ? profile.domains.filter((item) => finite(item.value)).sort((a, b) => b.value - a.value)
      : [];
    if (!domains.length) return null;
    const block = element("div", "native-strengths");
    append(
      block,
      element("p", "eyebrow", "Observed role domains"),
      element("p", "strengths-copy", "The overall role score stays broad; these domain percentiles show where the native performance profile is strongest."),
    );
    const list = element("div", "profile-pills");
    domains.forEach((item) => append(
      list,
      append(element("span"), element("small", "", item.label), element("strong", "", format(item.value, 1))),
    ));
    block.append(list);
    return block;
  }

  function nativeSection() {
    const section = element("section", "native-section");
    append(section, append(element("div", "subsection-heading"), element("p", "eyebrow", "Source-sport record"), element("h3", "", `${sportLabel(state.selected.sport)} · ${roleLabel(state.selected.sport, state.selected.role)}`)));
    const cards = element("div", "native-grid");
    const observed = scoreCard("observed", state.detail.native?.observed, { observed: true });
    const components = observedComponents(state.detail.native?.observed);
    if (components) observed.append(components);
    const reference = state.detail.native?.observed?.reference_athletes;
    if (finite(reference)) observed.append(element("p", "reference-note", `${format(reference)} athletes in the observed reference cohort.`));
    const forecast = scoreCard("forecast", state.detail.native?.forecast, { contributions: true });
    const season = state.detail.native?.forecast?.target_season;
    if (season) forecast.querySelector(".score-copy")?.append(` Target season: ${season}.`);
    append(cards, observed, forecast);
    section.append(cards);

    const strengths = nativeStrengths(state.detail.native_profile);
    if (strengths) section.append(strengths);

    const dimensions = state.detail.native_profile?.transferable_dimensions || [];
    if (dimensions.length) {
      const profile = element("details", "profile-details");
      profile.append(element("summary", "", "View mapped source-performance dimensions"));
      const list = element("div", "profile-pills");
      dimensions.forEach((item) => append(list, append(element("span"), element("small", "", item.label), element("strong", "", format(item.value, 1)))));
      profile.append(list);
      section.append(profile);
    }
    return section;
  }

  function targetTabs() {
    const wrapper = element("div", "target-controls");
    append(wrapper, append(element("div"), element("p", "eyebrow", "Choose a comparison"), element("h3", "", "Target sport and roles")));
    const tabs = element("div", "target-tabs");
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "Target sport");
    const sports = state.manifest.sports.filter((sport) => state.detail.targets?.[sport.id]);
    sports.forEach((sport, index) => {
      const tab = element("button", "target-tab", sport.label);
      tab.type = "button";
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", String(sport.id === state.targetSport));
      tab.tabIndex = sport.id === state.targetSport ? 0 : -1;
      tab.addEventListener("click", () => changeTarget(sport.id));
      tab.addEventListener("keydown", (event) => {
        let next = index;
        if (event.key === "ArrowRight") next = (index + 1) % sports.length;
        else if (event.key === "ArrowLeft") next = (index - 1 + sports.length) % sports.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = sports.length - 1;
        else return;
        event.preventDefault();
        changeTarget(sports[next].id, true);
      });
      tabs.append(tab);
    });
    wrapper.append(tabs);
    return wrapper;
  }

  function changeTarget(sport, focus = false) {
    state.targetSport = sport;
    renderResult();
    writeUrl();
    if (focus) result.querySelector(`[role="tab"][aria-selected="true"]`)?.focus();
    announce(`${sportLabel(sport)} selected. Role comparisons updated.`);
  }

  function roleCard(role, payload) {
    const card = element("article", "role-card");
    const header = element("header", "role-header");
    append(
      header,
      append(element("div"), element("p", "eyebrow", sportLabel(state.targetSport)), element("h4", "", payload.label || roleLabel(state.targetSport, role))),
      element("span", "evidence-label", words(payload.evidence_status || "research proxy")),
    );
    card.append(header);
    if (payload.limitation) card.append(element("p", "role-limitation", payload.limitation));
    const scores = element("div", "target-score-grid");
    append(
      scores,
      scoreCard("physical", payload.physical_only, { contributions: true }),
      scoreCard("transfer", payload.transfer_guesstimate, { contributions: true }),
    );
    card.append(scores);
    return card;
  }

  function targetSection() {
    const section = element("section", "target-section");
    section.append(targetTabs());
    const intro = element("div", "target-intro");
    const sameSport = state.selected.sport === state.targetSport;
    append(
      intro,
      element("p", "", sameSport
        ? "Physical-only estimates can be explored in the native league. Transfer guesstimates are intentionally not applicable without a different source sport."
        : `These ${sportLabel(state.targetSport)} comparisons reuse ${state.selected.name}’s build and mapped ${sportLabel(state.selected.sport)} performance profile.`),
      element("strong", "", "Cross-sport values are percentile guesstimates—not probabilities, scouting grades or evidence of sport-switch success."),
    );
    section.append(intro);
    const roles = state.detail.targets?.[state.targetSport]?.roles || {};
    const roleGrid = element("div", "role-grid");
    Object.entries(roles).forEach(([role, payload]) => roleGrid.append(roleCard(role, payload)));
    if (!Object.keys(roles).length) roleGrid.append(element("p", "empty-state", "No role results were exported for this target sport."));
    section.append(roleGrid);
    return section;
  }

  function renderResult() {
    result.replaceChildren(playerHeader(), nativeSection(), targetSection());
    result.setAttribute("aria-busy", "false");
  }

  function renderModelRecord() {
    const record = $("#model-record");
    record.replaceChildren();
    const model = state.manifest.model || {};
    const facts = element("dl", "model-facts");
    const entries = [
      ["Target contract", model.target_version || "Unavailable"],
      ["Role taxonomy", model.role_taxonomy_version || "Unavailable"],
      ["Bridge mapping", model.bridge_version || "Unavailable"],
      ["Frozen test season", model.frozen_test_season || "Unavailable"],
      ["Latest selectable athlete profiles", state.manifest.counts?.players || 0],
      ["Fitted physical role heads", model.evidence?.physical_models_fit ?? "Unavailable"],
      ["Supported physical-association heads", model.evidence?.physical_models_supported ?? "Unavailable"],
      ["Deployment-supported native forecasts", model.evidence?.native_models_deployment_supported ?? "Unavailable"],
      ["Target-proxy heads passing reconstruction gate", model.evidence?.bridge_target_proxy_heads_passing_gate ?? "Unavailable"],
    ];
    entries.forEach(([label, value]) => append(facts, append(element("div"), element("dt", "", label), element("dd", "", value))));
    record.append(facts);
    const limitations = element("ul", "limitations");
    (state.manifest.limitations || []).forEach((item) => limitations.append(element("li", "", item)));
    record.append(append(element("div", "limitations-block"), element("h3", "", "Required cautions"), limitations));
    const claimEntries = Object.entries(state.manifest.claims || {});
    if (claimEntries.length) {
      const claims = element("ul", "limitations");
      claimEntries.forEach(([kind, claim]) => claims.append(element("li", "", `${words(kind)}: ${String(claim)}`)));
      record.append(append(element("div", "limitations-block"), element("h3", "", "Artifact claim boundaries"), claims));
    }
  }

  function populateFilters() {
    const select = $("#source-sport");
    state.manifest.sports.forEach((sport) => {
      const option = element("option", "", sport.label);
      option.value = sport.id;
      select.append(option);
    });
    select.addEventListener("change", (event) => {
      state.sourceSport = event.target.value;
      renderPlayerList();
    });
    $("#player-search").addEventListener("input", (event) => {
      state.query = event.target.value;
      renderPlayerList();
    });
  }

  async function initialise() {
    try {
      state.manifest = await fetchJson("data/manifest.json");
      state.players = Array.isArray(state.manifest.players) ? state.manifest.players : [];
      populateFilters();
      renderPlayerList();
      renderModelRecord();
      const seasons = state.manifest.snapshot?.latest_seasons || [];
      $("#snapshot-note").textContent = `${state.players.length.toLocaleString("en-US")} latest selectable athlete profiles · seasons ${seasons.join(", ") || "unavailable"}`;
      const params = new URLSearchParams(window.location.search);
      const requestedPlayer = params.get("player");
      const requestedSport = params.get("sport");
      const player = state.players.find((item) => item.id === requestedPlayer)
        || state.players.find((item) => item.id === state.manifest.defaults?.player_id)
        || state.players[0];
      if (!player) throw new Error("The export contains no active player profiles.");
      $("#explorer-grid").setAttribute("aria-busy", "false");
      await selectPlayer(player, requestedSport || state.manifest.defaults?.target_sport);
    } catch (error) {
      const notice = $("#app-error");
      notice.hidden = false;
      notice.textContent = "The all-role export could not be loaded. Run the portal builder, then serve this directory over a local web server.";
      $("#explorer-grid").setAttribute("aria-busy", "false");
      result.setAttribute("aria-busy", "false");
      announce("The all-role explorer could not be loaded.");
    }
  }

  initialise();
})();
