/* Compact read-only viewer. Inference and evidence gates run in the shared exporter. */
"use strict";

(() => {
  const $ = (selector) => document.querySelector(selector);
  const dataRoot = new URL("../data/", document.baseURI);
  const state = {
    manifest: null,
    players: [],
    selected: null,
    detail: null,
    targetSport: null,
    targetRole: null,
    basis: "physical",
    sourceSport: "all",
    query: "",
    request: 0,
  };
  const cache = new Map();
  const result = $("#result");
  const playerList = $("#player-list");

  const statusCopy = {
    available: "Available",
    eligible: "Observed",
    low_sample: "Low sample",
    not_observed: "Not observed",
    not_applicable_without_source_performance: "Not applicable in native sport",
    withheld_no_fitted_model: "Withheld · no fitted model",
    withheld_missing_height_or_weight: "Withheld · missing body measurements",
    withheld_missing_fixed_bridge_dimensions: "Withheld · mapped performance missing",
    withheld_missing_required_dimensions: "Withheld · mapped performance missing",
    withheld_proxy_model_failed_baseline_gate: "Withheld · proxy evidence gate failed",
    withheld_target_proxy_reconstruction_failed_gate: "Withheld · proxy evidence gate failed",
    withheld_source_performance_not_eligible: "Withheld · source season ineligible",
    withheld_out_of_domain: "Withheld · outside reference domain",
    withheld_insufficient_reference: "Withheld · small body reference",
    insufficient_reference: "Small body reference",
  };

  const featureNames = {
    height_cm: "Height",
    weight_kg: "Weight",
    bmi: "BMI",
    age: "Age",
    observed_role_percentile: "Prior observed role score",
    availability_percentile: "Prior availability",
    sustained_3y_percentile: "Sustained three-year form",
    dimension_scoring_finishing_percentile: "Scoring / finishing profile",
    dimension_creation_distribution_percentile: "Creation / distribution profile",
    dimension_possession_security_percentile: "Possession security profile",
    dimension_defensive_disruption_percentile: "Defensive disruption profile",
    dimension_progression_territory_percentile: "Progression / territory profile",
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
    return String(value || "")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function searchable(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/\p{Diacritic}/gu, "")
      .toLocaleLowerCase();
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
    return String(name || "?")
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0])
      .join("")
      .toUpperCase();
  }

  function announce(message) {
    $("#announcement").textContent = message;
  }

  function featureLabel(feature) {
    return featureNames[feature] || words(feature).replace(" Percentile", "");
  }

  async function fetchJson(path) {
    const relative = String(path).replace(/^data\//, "");
    const url = new URL(relative, dataRoot);
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
      const sourceMatches = state.sourceSport === "all" || player.sport === state.sourceSport;
      const textMatches = !needle || searchable(
        `${player.name} ${player.team || ""} ${player.role || ""} ${player.position || ""}`,
      ).includes(needle);
      return sourceMatches && textMatches;
    });
    $("#player-count").textContent = matches.length.toLocaleString("en-US");
    playerList.replaceChildren();
    if (!matches.length) {
      playerList.append(element("p", "empty-state", "No athletes match this search."));
      return;
    }
    let visible = matches.slice(0, 160);
    if (
      state.selected
      && matches.some((player) => player.id === state.selected.id)
      && !visible.some((player) => player.id === state.selected.id)
    ) {
      visible = [state.selected, ...visible.slice(0, 159)];
    }
    const fragment = document.createDocumentFragment();
    visible.forEach((player) => {
      const button = element("button", "player-option");
      button.type = "button";
      button.dataset.playerId = player.id;
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", String(player.id === state.selected?.id));
      const avatar = element("span", "avatar", initials(player.name));
      avatar.setAttribute("aria-hidden", "true");
      const copy = element("span", "player-copy");
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
      playerList.append(element("p", "list-limit", `Showing ${visible.length}. Search to narrow the list.`));
    }
  }

  function updatePlayerSelection() {
    let selectedVisible = false;
    playerList.querySelectorAll("[data-player-id]").forEach((button) => {
      const active = button.dataset.playerId === state.selected?.id;
      button.setAttribute("aria-selected", String(active));
      selectedVisible ||= active;
    });
    if (state.selected && !selectedVisible) renderPlayerList();
  }

  function targetRoles(sport = state.targetSport) {
    const payloads = state.detail?.targets?.[sport]?.roles || {};
    const declared = sportRecord(sport)?.roles || [];
    const ordered = declared.filter((role) => payloads[role.id]);
    const seen = new Set(ordered.map((role) => role.id));
    Object.entries(payloads).forEach(([id, payload]) => {
      if (!seen.has(id)) ordered.push({ id, label: payload.label || words(id) });
    });
    return ordered;
  }

  function validSport(preferred) {
    const available = Object.keys(state.detail?.targets || {});
    if (preferred && available.includes(preferred)) return preferred;
    if (state.selected?.sport && available.includes(state.selected.sport)) return state.selected.sport;
    return available[0] || null;
  }

  function defaultRole(sport, preferred) {
    const roles = targetRoles(sport);
    if (preferred && roles.some((role) => role.id === preferred)) return preferred;
    if (sport === state.selected?.sport && roles.some((role) => role.id === state.selected.role)) {
      return state.selected.role;
    }
    return roles[0]?.id || null;
  }

  function defaultBasis(sport, preferred) {
    if (sport === state.selected?.sport) return "physical";
    return ["physical", "transfer"].includes(preferred) ? preferred : "transfer";
  }

  async function selectPlayer(player, preferred = {}) {
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
      state.targetSport = validSport(preferred.sport || state.targetSport);
      state.targetRole = defaultRole(state.targetSport, preferred.role);
      state.basis = defaultBasis(state.targetSport, preferred.basis || state.basis);
      renderResult();
      writeUrl();
      announce(
        `${player.name} selected. Comparing ${sportLabel(state.targetSport)} ${roleLabel(state.targetSport, state.targetRole)}.`,
      );
    } catch (_) {
      if (request !== state.request) return;
      const box = element("div", "result-error");
      append(
        box,
        element("h2", "", "This athlete could not be loaded"),
        element("p", "", "The shared player result is missing or unreadable."),
      );
      const retry = element("button", "retry", "Try again");
      retry.type = "button";
      retry.addEventListener("click", () => selectPlayer(player, preferred));
      box.append(retry);
      result.replaceChildren(box);
      result.setAttribute("aria-busy", "false");
      announce("The selected athlete could not be loaded.");
    }
  }

  function writeUrl() {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("player", state.selected.id);
      url.searchParams.set("sport", state.targetSport);
      url.searchParams.set("role", state.targetRole);
      url.searchParams.set("basis", state.basis);
      window.history.replaceState(null, "", url);
    } catch (_) {
      /* History access is optional in embedded previews. */
    }
  }

  function selectedRolePayload() {
    return state.detail?.targets?.[state.targetSport]?.roles?.[state.targetRole] || null;
  }

  function selectedScore() {
    const payload = selectedRolePayload();
    return state.basis === "transfer" ? payload?.transfer_guesstimate : payload?.physical_only;
  }

  function scoreAvailable(score, observed = false) {
    if (!score || !finite(score.value)) return false;
    return observed ? !["not_observed", "withheld"].includes(score.status) : score.status === "available";
  }

  function statusLabel(score, observed = false) {
    if (scoreAvailable(score, observed)) {
      if (score?.support_status === "association_gate_supported") return "Supported association";
      if (String(score?.support_status || "").startsWith("experimental")) return "Exploratory proxy";
      if (score?.deployment_support === "experimental_unsupported") return "Experimental forecast";
      return statusCopy[score.status] || "Available";
    }
    return statusCopy[score?.status] || words(score?.status || "Evidence unavailable");
  }

  function statusClass(score, observed = false) {
    if (!scoreAvailable(score, observed)) return "withheld";
    return String(score?.support_status || score?.deployment_support || "").startsWith("experimental")
      ? "experimental"
      : "";
  }

  function renderHeader() {
    const player = state.selected;
    const header = element("header", "athlete-header");
    const title = element("div", "athlete-title");
    const avatar = element("span", "avatar", initials(player.name));
    avatar.setAttribute("aria-hidden", "true");
    append(
      title,
      avatar,
      append(element("div"), element("p", "eyebrow", "Selected athlete"), element("h2", "", player.name)),
    );
    append(
      header,
      append(element("div", "athlete-top"), title, element("span", "source-chip", `${sportLabel(player.sport)} source`)),
    );
    const meta = element("p", "athlete-meta");
    [roleLabel(player.sport, player.role), player.position, player.team || "Team unavailable", `Season ${player.season}`]
      .filter(Boolean)
      .forEach((item) => meta.append(element("span", "", item)));
    header.append(meta);
    const measurements = element("dl", "measurements");
    const values = [
      ["Height", finite(player.height_cm) ? `${format(player.height_cm, 1)} cm` : "Unavailable"],
      ["Weight", finite(player.weight_kg) ? `${format(player.weight_kg, 1)} kg` : "Unavailable"],
      ["Age", finite(player.age) ? format(player.age, 1) : "Unavailable"],
      [
        finite(player.opportunity) ? "Opportunity" : "Roster weeks",
        finite(player.opportunity)
          ? format(player.opportunity)
          : finite(player.rostered_weeks) ? format(player.rostered_weeks) : "Unavailable",
      ],
    ];
    values.forEach(([label, value]) => {
      append(measurements, append(element("div"), element("dt", "", label), element("dd", "", value)));
    });
    header.append(measurements);
    return header;
  }

  function changeSport(sport, focus = false) {
    state.targetSport = sport;
    state.targetRole = defaultRole(sport, null);
    state.basis = defaultBasis(sport, null);
    renderResult();
    writeUrl();
    if (focus) result.querySelector(`[data-target-sport="${sport}"]`)?.focus();
    announce(`${sportLabel(sport)} selected. Target role reset to ${roleLabel(sport, state.targetRole)}.`);
  }

  function renderControls() {
    const section = element("section", "target-controls");
    const row = element("div", "control-row");
    const sportControl = element("div");
    sportControl.append(element("span", "control-label", "Target sport"));
    const tabs = element("div", "sport-tabs");
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "Target sport");
    const sports = state.manifest.sports.filter((sport) => state.detail.targets?.[sport.id]);
    sports.forEach((sport, index) => {
      const button = element("button", "sport-tab", sport.label);
      button.type = "button";
      button.dataset.targetSport = sport.id;
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", String(sport.id === state.targetSport));
      button.tabIndex = sport.id === state.targetSport ? 0 : -1;
      button.addEventListener("click", () => changeSport(sport.id));
      button.addEventListener("keydown", (event) => {
        let next = index;
        if (event.key === "ArrowRight") next = (index + 1) % sports.length;
        else if (event.key === "ArrowLeft") next = (index - 1 + sports.length) % sports.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = sports.length - 1;
        else return;
        event.preventDefault();
        changeSport(sports[next].id, true);
      });
      tabs.append(button);
    });
    sportControl.append(tabs);

    const roleControl = element("div");
    const roleLabelElement = element("label", "control-label", "Target role");
    roleLabelElement.htmlFor = "target-role";
    const select = element("select", "role-select");
    select.id = "target-role";
    targetRoles().forEach((role) => {
      const option = element("option", "", role.label || words(role.id));
      option.value = role.id;
      option.selected = role.id === state.targetRole;
      select.append(option);
    });
    select.addEventListener("change", (event) => {
      state.targetRole = event.target.value;
      renderResult();
      writeUrl();
      $("#target-role")?.focus();
      announce(`${roleLabel(state.targetSport, state.targetRole)} selected.`);
    });
    append(roleControl, roleLabelElement, select);
    append(row, sportControl, roleControl);
    section.append(row);
    const native = state.selected.sport === state.targetSport;
    section.append(element(
      "p",
      "target-note",
      native
        ? "Native-sport view: transfer is not applicable; compare the selected role's build association with the player's observed record below."
        : `Cross-sport view: ${sportLabel(state.selected.sport)} performance dimensions are mapped into a ${sportLabel(state.targetSport)} role analogy.`,
    ));
    return section;
  }

  function renderScoreCard(payload) {
    const score = selectedScore();
    const available = scoreAvailable(score);
    const card = element("section", "score-card");
    const heading = state.basis === "transfer" ? "Transfer efficacy guesstimate" : "Physical-only estimate";
    append(
      card,
      append(
        element("div", "score-top"),
        element("h3", "", heading),
        element("span", `status ${statusClass(score)}`, statusLabel(score)),
      ),
    );

    const toggle = element("div", "basis-toggle");
    toggle.setAttribute("aria-label", "Estimate basis");
    const options = [
      ["transfer", "Build + mapped performance"],
      ["physical", "Build / age association"],
    ];
    options.forEach(([basis, label]) => {
      const button = element("button", "", label);
      button.type = "button";
      button.setAttribute("aria-pressed", String(state.basis === basis));
      if (basis === "transfer" && state.targetSport === state.selected.sport) button.disabled = true;
      button.addEventListener("click", () => {
        state.basis = basis;
        renderResult();
        writeUrl();
        result.querySelector(`.basis-toggle button[aria-pressed="true"]`)?.focus();
        announce(`${basis === "transfer" ? "Build plus mapped performance" : "Build and age association"} selected.`);
      });
      toggle.append(button);
    });
    card.append(toggle);

    const value = element("div", "score-value", available ? format(score.value, 1) : "—");
    if (available) value.append(element("small", "", "role percentile"));
    card.append(value);
    card.append(element(
      "p",
      "score-description",
      state.basis === "transfer"
        ? "Exploratory target-role percentile from build plus mapped source-sport performance. Not a switch probability."
        : "Target-role outcome association from height, weight, BMI and age. This is not body similarity or causality.",
    ));
    if (available) {
      const track = element("div", "score-track");
      track.setAttribute("role", "img");
      track.setAttribute("aria-label", `${heading}: ${format(score.value, 1)} role percentile`);
      const fill = element("span");
      fill.style.width = `${Math.max(0, Math.min(100, score.value))}%`;
      track.append(fill);
      card.append(track);
    }
    const range = score?.analogy_sensitivity_range;
    if (Array.isArray(range) && range.length === 2 && range.every(finite)) {
      append(
        card,
        append(
          element("div", "range"),
          element("span", "", "Model-error sensitivity"),
          element("strong", "", `${format(range[0], 1)}–${format(range[1], 1)}`),
        ),
      );
    }
    if (!available) {
      card.append(element(
        "p",
        "warning",
        score?.reason ? `Reason: ${words(score.reason)}` : "No supported number is available. Withheld does not mean zero.",
      ));
    } else if (score?.evidence_warning) {
      card.append(element("p", "warning", score.evidence_warning));
    }
    if (score?.saturation_warning) {
      card.append(element("p", "warning saturation", score.saturation_warning));
    }
    return card;
  }

  function bodyBand(value) {
    if (value >= 75) return "Highly central build";
    if (value >= 40) return "Typical build";
    if (value >= 15) return "Less typical build";
    return "Peripheral build";
  }

  function renderBodyCard(payload) {
    const body = payload?.body_fit;
    const card = element("section", "body-card");
    const available = body?.status === "available" && finite(body.value);
    append(
      card,
      append(
        element("div", "body-top"),
        element("h3", "", "Body fit"),
        element("span", `status ${available ? "" : "withheld"}`, available ? "Descriptive" : statusCopy[body?.status] || "Domain only"),
      ),
    );
    if (available) {
      const value = element("div", "body-value", format(body.value, 0));
      value.append(element("small", "", "/ 100 centrality"));
      card.append(value, element("p", "body-band", bodyBand(body.value)));
      const track = element("div", "body-track");
      track.setAttribute("aria-hidden", "true");
      for (let index = 0; index < 10; index += 1) {
        track.append(element("i", index < Math.round(body.value / 10) ? "filled" : ""));
      }
      card.append(track, element("p", "body-copy", body.note));
      const meta = element("div", "body-meta");
      const center = body.reference_center;
      if (center && finite(center.height_cm) && finite(center.weight_kg)) {
        append(
          meta,
          append(element("span"), element("span", "", "Role center"), element("strong", "", `${format(center.height_cm, 1)} cm · ${format(center.weight_kg, 1)} kg`)),
        );
      }
      append(
        meta,
        append(element("span"), element("span", "", "Reference"), element("strong", "", `${format(body.reference_athletes)} athletes`)),
      );
      if (body.outside_1_99_reference) {
        meta.append(element("span", "", "Outside the role cohort's 1st–99th percentile height/weight bounds."));
      }
      card.append(meta);
      return card;
    }

    const ood = payload?.physical_only?.ood;
    const domain = ood?.physical_status || ood?.status;
    const inDomain = ["in_domain", "in_domain_with_age_warning"].includes(domain);
    card.append(element("div", "body-value", inDomain ? "In range" : domain === "out_of_domain" ? "Outside" : "—"));
    card.append(element(
      "p",
      "body-copy",
      body
        ? "A numerical build-centrality percentile needs both measurements and a sufficient target-role reference cohort."
        : "The shared export predates the body-centrality field. Rebuild it to show numerical body fit.",
    ));
    if (finite(ood?.physical_max_robust_z)) {
      const meta = element("div", "body-meta");
      append(
        meta,
        append(element("span"), element("span", "", "Max robust distance"), element("strong", "", format(ood.physical_max_robust_z, 2))),
      );
      meta.append(element("span", "", "Reference-domain distance is a diagnostic, not performance."));
      card.append(meta);
    }
    return card;
  }

  function renderNativeStrip() {
    const strip = element("section", "native-strip");
    strip.setAttribute("aria-label", "Native sport validation context");
    const observed = state.detail.native?.observed;
    const forecast = state.detail.native?.forecast;
    const domains = (state.detail.native_profile?.domains || [])
      .filter((item) => finite(item.value))
      .sort((a, b) => b.value - a.value);
    const items = [
      ["Native observed", scoreAvailable(observed, true) ? format(observed.value, 1) : "—", statusLabel(observed, true)],
      ["Next-season forecast", scoreAvailable(forecast) ? format(forecast.value, 1) : "—", statusLabel(forecast)],
      ["Strongest native domain", domains[0] ? format(domains[0].value, 1) : "—", domains[0] ? words(domains[0].label) : "Unavailable"],
    ];
    items.forEach(([label, value, note]) => {
      append(
        strip,
        append(
          element("div", "native-item"),
          element("span", "", label),
          element("strong", "", value),
          element("small", "", note),
        ),
      );
    });
    return strip;
  }

  function renderWhy() {
    const score = selectedScore();
    const section = element("section", "why");
    section.append(element("h3", "", "Why this estimate"));
    const contributions = Array.isArray(score?.top_contributions) ? score.top_contributions.slice(0, 3) : [];
    if (!contributions.length) {
      section.append(element(
        "p",
        "why-empty",
        score?.reason ? `No contribution breakdown: ${words(score.reason)}.` : "No contribution breakdown is available for this withheld result.",
      ));
      return section;
    }
    const list = element("ol", "reason-list");
    contributions.forEach((reason) => {
      const contribution = finite(reason.contribution)
        ? `${reason.contribution >= 0 ? "+" : ""}${format(reason.contribution, 1)} model pts`
        : "Effect unavailable";
      append(
        list,
        append(
          element("li"),
          element("span", "", featureLabel(reason.feature)),
          element("strong", "", contribution),
          reason.imputed ? element("small", "", "Model-imputed input") : null,
        ),
      );
    });
    section.append(list);
    return section;
  }

  function renderEvidence(payload) {
    const score = selectedScore();
    const details = element("details", "evidence");
    details.append(element("summary", "", "Evidence, diagnostics and role limitation"));
    const content = element("div", "evidence-content");
    const list = element("ul", "evidence-list");
    const entries = [];
    if (score?.evidence_class) entries.push(`Evidence class: ${words(score.evidence_class)}`);
    if (score?.support_status) entries.push(`Support: ${words(score.support_status)}`);
    if (score?.evaluation_status) entries.push(`Evaluation: ${words(score.evaluation_status)}`);
    if (finite(score?.reference_rows)) entries.push(`Model reference rows: ${format(score.reference_rows)}`);
    if (score?.ood?.status) entries.push(`Feature domain: ${words(score.ood.status)}`);
    if (score?.semantic_bridge_grade) entries.push(`Semantic bridge: ${words(score.semantic_bridge_grade)}`);
    if (score?.target_proxy_reconstruction_gate) {
      entries.push(`Target proxy reconstruction: ${words(score.target_proxy_reconstruction_gate)}`);
    }
    if (Array.isArray(score?.dimensions) && score.dimensions.length) {
      entries.push(`Mapped dimensions: ${score.dimensions.map(words).join(", ")}`);
    }
    if (score?.range_warning) entries.push(score.range_warning);
    if (score?.evidence_warning) entries.push(score.evidence_warning);
    if (!entries.length) entries.push("No additional model diagnostics were exported for this result.");
    entries.forEach((entry) => list.append(element("li", "", entry)));
    const roleNote = element(
      "p",
      "role-limit",
      payload?.limitation || "This public-stat role target is incomplete and should not be treated as total player quality.",
    );
    append(content, list, roleNote);
    details.append(content);
    return details;
  }

  function renderResult() {
    const payload = selectedRolePayload();
    const content = element("div", "results");
    append(
      content,
      append(element("div", "result-grid"), renderScoreCard(payload), renderBodyCard(payload)),
      renderNativeStrip(),
      renderWhy(),
      renderEvidence(payload),
    );
    result.replaceChildren(renderHeader(), renderControls(), content);
    result.setAttribute("aria-busy", "false");
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
      state.manifest = await fetchJson("manifest.json");
      state.players = Array.isArray(state.manifest.players) ? state.manifest.players : [];
      populateFilters();
      renderPlayerList();
      const seasons = state.manifest.snapshot?.latest_seasons || [];
      $("#snapshot-note").textContent = `${state.players.length.toLocaleString("en-US")} latest profiles · seasons ${seasons.join(", ") || "unavailable"}`;
      const params = new URLSearchParams(window.location.search);
      const player = state.players.find((item) => item.id === params.get("player"))
        || state.players.find((item) => item.id === state.manifest.defaults?.player_id)
        || state.players[0];
      if (!player) throw new Error("The shared export has no selectable athletes.");
      $("#explorer-grid").setAttribute("aria-busy", "false");
      await selectPlayer(player, {
        sport: params.get("sport") || state.manifest.defaults?.target_sport,
        role: params.get("role"),
        basis: params.get("basis"),
      });
    } catch (_) {
      const notice = $("#app-error");
      notice.hidden = false;
      notice.textContent = "The shared all-role export could not be loaded. Build it first, then use the local portal server.";
      $("#explorer-grid").setAttribute("aria-busy", "false");
      result.setAttribute("aria-busy", "false");
      announce("The compact explorer could not be loaded.");
    }
  }

  initialise();
})();
