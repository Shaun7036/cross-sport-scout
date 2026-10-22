/* Plain-language explorer over the shared all-role export. */
"use strict";

(() => {
  const dataRoot = new URL("../data/", document.baseURI);
  const listLimit = 160;
  const featureNames = {
    height_cm: "height",
    weight_kg: "weight",
    bmi: "height-to-weight balance",
    age: "age",
    observed_role_percentile: "recent performance in their own role",
    availability_percentile: "availability",
    sustained_3y_percentile: "sustained form over three seasons",
    dimension_scoring_finishing_percentile: "scoring and finishing",
    dimension_creation_distribution_percentile: "creation and distribution",
    dimension_possession_security_percentile: "possession security",
    dimension_defensive_disruption_percentile: "defensive disruption",
    dimension_progression_territory_percentile: "progression and territory gain",
    dimension_discipline_efficiency_percentile: "discipline and efficiency",
    dimension_recovery_rebounding_percentile: "recovery and rebounding",
  };
  const noScoreReasons = {
    abstain_no_public_label: "Public data does not provide a credible individual performance measure for this role.",
    abstain_source_rights_and_label_limit: "The available public data is not suitable for a credible score in this role.",
    not_applicable_without_source_performance: "Choose another sport to see a cross-sport playing-style estimate.",
    withheld_no_fitted_model: "There was not enough reliable data to score this role.",
    withheld_missing_height_or_weight: "Height or weight is missing.",
    withheld_missing_fixed_bridge_dimensions: "The source sport does not provide enough comparable playing-style data.",
    withheld_missing_required_dimensions: "The source sport does not provide enough comparable playing-style data.",
    withheld_proxy_model_failed_baseline_gate: "This estimate was too unreliable in testing.",
    withheld_target_proxy_reconstruction_failed_gate: "This estimate was too unreliable in testing.",
    withheld_target_role_forward_profile_failed_gate: "This estimate was too unreliable in forward testing.",
    withheld_source_performance_not_eligible: "The player did not have enough playing time for a reliable source profile.",
    withheld_out_of_domain: "This athlete is too different from the players used to build this comparison.",
    withheld_insufficient_reference: "Too few players in this role have usable measurements.",
    withheld_same_sport_transfer: "Choose another sport to see a cross-sport playing-style estimate.",
    low_sample: "The player did not have enough playing time for a full-strength result.",
    missing: "The information needed for this result is missing.",
    not_observed: "There was not enough season information to show this result.",
    out_of_domain: "This athlete is too different from the players used to build this comparison.",
  };

  const state = {
    manifest: null,
    players: [],
    selected: null,
    detail: null,
    targetSport: null,
    targetRole: null,
    basis: "transfer",
    sourceSport: "all",
    query: "",
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

  function clamp(value, low = 0, high = 100) {
    return Math.min(high, Math.max(low, value));
  }

  function ordinal(value) {
    const rounded = Math.round(value);
    const lastTwo = rounded % 100;
    if (lastTwo >= 11 && lastTwo <= 13) return `${rounded}th`;
    const suffix = { 1: "st", 2: "nd", 3: "rd" }[rounded % 10] || "th";
    return `${rounded}${suffix}`;
  }

  function words(value) {
    return String(value || "")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function possessive(name) {
    return /s$/i.test(name) ? `${name}'` : `${name}'s`;
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

  function formatHeight(cm) {
    if (!finite(cm)) return "Not listed";
    const inches = Math.round(cm / 2.54);
    return `${Math.floor(inches / 12)}′${inches % 12}″ · ${format(cm)} cm`;
  }

  function formatWeight(kg) {
    if (!finite(kg)) return "Not listed";
    return `${format(kg * 2.20462)} lb · ${format(kg)} kg`;
  }

  function scoreAvailable(score) {
    return score?.status === "available" && finite(score.value);
  }

  function observedAvailable(score) {
    return finite(score?.value) && !["not_observed", "unavailable"].includes(score?.status);
  }

  async function fetchJson(path) {
    const relative = String(path || "").replace(/^data\//, "");
    const url = new URL(relative, dataRoot);
    if (url.origin !== window.location.origin || !url.pathname.startsWith(dataRoot.pathname)) {
      throw new Error("The requested file is outside this local project.");
    }
    const response = await fetch(url, { cache: "no-store", credentials: "same-origin" });
    if (!response.ok) throw new Error(`The saved result could not be read (${response.status}).`);
    return response.json();
  }

  function sportConfig(sport) {
    return state.manifest?.sports?.find((item) => item.id === sport);
  }

  function sportLabel(sport) {
    return sportConfig(sport)?.label || String(sport || "").toUpperCase();
  }

  function roleConfig(sport, role) {
    return sportConfig(sport)?.roles?.find((item) => item.id === role);
  }

  function roleLabel(sport, role) {
    return roleConfig(sport, role)?.label || words(role);
  }

  function reasonFor(score, fallback) {
    return noScoreReasons[score?.status]
      || fallback
      || "The model did not have enough familiar evidence to show a responsible number.";
  }

  function comparisonBand(value) {
    if (value >= 90) return "Top-tier comparison";
    if (value >= 75) return "Strong comparison";
    if (value >= 60) return "Above-average comparison";
    if (value >= 40) return "Around the middle";
    if (value >= 25) return "Below-average comparison";
    return "Weak comparison";
  }

  function bodyBand(value) {
    if (value >= 75) return "Very typical for this role";
    if (value >= 40) return "Fairly typical for this role";
    if (value >= 15) return "Less typical for this role";
    return "Very unusual for this role";
  }

  function statusInfo(score) {
    if (!scoreAvailable(score)) return { label: "No score shown", className: "none" };
    if (score.support_status === "association_gate_supported") {
      return { label: "Pattern held up in testing", className: "" };
    }
    if (String(score.support_status || score.evidence_class || "").includes("experimental")) {
      return { label: "Early estimate — use cautiously", className: "caution" };
    }
    return { label: "Experimental comparison", className: "caution" };
  }

  function contributionSentence(contribution) {
    const feature = featureNames[contribution?.feature] || words(contribution?.feature).toLowerCase();
    if (!finite(contribution?.contribution)) return `${words(feature)} was included in the comparison.`;
    return contribution.contribution >= 0
      ? `Their ${feature} pushes this estimate higher.`
      : `Their ${feature} pulls this estimate lower.`;
  }

  function explanationSentences(score, payload, basis) {
    const target = `${sportLabel(state.targetSport)} ${payload.label || roleLabel(state.targetSport, state.targetRole)}`;
    if (!scoreAvailable(score)) {
      return [
        reasonFor(score),
        "No score shown is not a zero; it means the model chose not to make this comparison.",
      ];
    }

    const subject = basis === "transfer" ? "body and playing style" : "body and age";
    const sentences = [
      `Using ${subject}, the model places this athlete in the ${comparisonBand(score.value).toLowerCase()} range for ${target}.`,
    ];
    const contributions = Array.isArray(score.top_contributions)
      ? score.top_contributions.filter((item) => item && item.feature).slice(0, 2)
      : [];
    contributions.forEach((item) => sentences.push(contributionSentence(item)));
    if (sentences.length === 1) {
      sentences.push("The saved result does not include a clear single factor behind the estimate.");
    }
    if (sentences.length === 2) {
      sentences.push("Treat this as a clue for comparison, not proof that the athlete could change sports.");
    }
    return sentences.slice(0, 3);
  }

  function percentileMeaning(value, label) {
    if (value >= 99.5) {
      return `This result reaches the top of the ${label} comparison scale. The model cannot measure differences beyond that limit.`;
    }
    const rounded = Math.round(value);
    return `This result is higher than about ${rounded} of every 100 players in the ${label} comparison group.`;
  }

  function selectedPayload() {
    return state.detail?.targets?.[state.targetSport]?.roles?.[state.targetRole] || null;
  }

  function orderedRoles(sport) {
    const payloadRoles = state.detail?.targets?.[sport]?.roles || {};
    const configured = sportConfig(sport)?.roles || [];
    const seen = new Set();
    const roles = [];
    configured.forEach((role) => {
      if (payloadRoles[role.id]) {
        roles.push({ ...role, label: payloadRoles[role.id].label || role.label });
        seen.add(role.id);
      }
    });
    Object.entries(payloadRoles).forEach(([id, payload]) => {
      if (!seen.has(id)) roles.push({ id, label: payload.label || words(id) });
    });
    return roles;
  }

  function roleExists(sport, role) {
    return orderedRoles(sport).some((item) => item.id === role);
  }

  function chooseRole(sport, preferred) {
    const roles = orderedRoles(sport);
    if (roles.some((role) => role.id === preferred)) return preferred;
    if (sport === state.selected?.sport && roles.some((role) => role.id === state.selected?.role)) {
      return state.selected.role;
    }
    return roles[0]?.id || null;
  }

  function availableTargetSports() {
    const targets = state.detail?.targets || {};
    const ordered = (state.manifest?.sports || []).filter((sport) => targets[sport.id]);
    Object.keys(targets).forEach((id) => {
      if (!ordered.some((sport) => sport.id === id)) ordered.push({ id, label: sportLabel(id), roles: [] });
    });
    return ordered;
  }

  function normaliseSelection(preferred = {}) {
    const sports = availableTargetSports();
    const preferredSport = preferred.sport || state.targetSport;
    state.targetSport = sports.some((sport) => sport.id === preferredSport)
      ? preferredSport
      : sports.find((sport) => sport.id !== state.selected?.sport)?.id || sports[0]?.id || null;
    state.targetRole = chooseRole(state.targetSport, preferred.role || state.targetRole);
    const requestedBasis = preferred.basis || state.basis;
    state.basis = requestedBasis === "physical" || requestedBasis === "transfer" ? requestedBasis : "transfer";
    if (state.targetSport === state.selected?.sport) state.basis = "physical";
  }

  function updateUrl() {
    if (!state.selected || !state.targetSport || !state.targetRole) return;
    const url = new URL(window.location.href);
    url.searchParams.set("player", state.selected.id);
    url.searchParams.set("sport", state.targetSport);
    url.searchParams.set("role", state.targetRole);
    url.searchParams.set("basis", state.basis);
    window.history.replaceState(null, "", url);
  }

  function measurement(label, value) {
    const wrapper = element("div");
    append(wrapper, element("dt", "", label), element("dd", "", value));
    return wrapper;
  }

  function athleteHeader() {
    const player = state.selected;
    const section = element("header", "athlete");
    const top = element("div", "athlete-top");
    const name = element("div", "athlete-name");
    append(
      name,
      element("span", "avatar", initials(player.name)),
      append(
        element("div"),
        element("p", "kicker", "Starting athlete"),
        element("h2", "", player.name),
      ),
    );
    append(top, name, element("span", "source-label", sportLabel(player.sport)));

    const meta = element("p", "athlete-meta");
    [player.team, roleLabel(player.sport, player.role), player.position && player.position !== player.role ? player.position : null]
      .filter(Boolean)
      .forEach((value) => meta.append(element("span", "", value)));

    const measurements = element("dl", "measurements");
    append(
      measurements,
      measurement("Height", formatHeight(player.height_cm)),
      measurement("Weight", formatWeight(player.weight_kg)),
      measurement("Age", finite(player.age) ? format(player.age) : "Not listed"),
      measurement("Season", player.season || "Not listed"),
    );
    return append(section, top, meta, measurements);
  }

  function comparisonControls() {
    const section = element("section", "comparison-controls");
    const selectGrid = element("div", "select-grid");

    const sportWrap = element("div");
    const sportLabelElement = element("label", "", "Compare with this sport");
    sportLabelElement.htmlFor = "target-sport";
    const sportSelect = element("select");
    sportSelect.id = "target-sport";
    availableTargetSports().forEach((sport) => {
      const option = element("option", "", sport.label || sportLabel(sport.id));
      option.value = sport.id;
      option.selected = sport.id === state.targetSport;
      sportSelect.append(option);
    });
    sportSelect.addEventListener("change", () => {
      const wasNativeSport = state.targetSport === state.selected.sport;
      state.targetSport = sportSelect.value;
      state.targetRole = chooseRole(state.targetSport, null);
      if (state.targetSport === state.selected.sport) state.basis = "physical";
      else if (wasNativeSport) state.basis = "transfer";
      updateUrl();
      renderResult("#target-sport");
      announceResult();
    });
    append(sportWrap, sportLabelElement, sportSelect);

    const roleWrap = element("div");
    const roleLabelElement = element("label", "", "Role in that sport");
    roleLabelElement.htmlFor = "target-role";
    const roleSelect = element("select");
    roleSelect.id = "target-role";
    orderedRoles(state.targetSport).forEach((role) => {
      const option = element("option", "", role.label);
      option.value = role.id;
      option.selected = role.id === state.targetRole;
      roleSelect.append(option);
    });
    roleSelect.addEventListener("change", () => {
      state.targetRole = roleSelect.value;
      updateUrl();
      renderResult("#target-role");
      announceResult();
    });
    append(roleWrap, roleLabelElement, roleSelect);
    append(selectGrid, sportWrap, roleWrap);

    const fieldset = element("fieldset", "basis");
    fieldset.append(element("legend", "", "What should the comparison use?"));
    const options = element("div", "basis-options");
    const choices = [
      {
        value: "transfer",
        label: "Body + playing style",
        help: "Uses build and broad strengths shown in games.",
      },
      {
        value: "physical",
        label: "Body + age only",
        help: "Ignores game performance and uses physical profile only.",
      },
    ];
    choices.forEach((choice) => {
      const option = element("label", "basis-option");
      const input = element("input");
      input.type = "radio";
      input.name = "estimate-basis";
      input.value = choice.value;
      input.checked = choice.value === state.basis;
      input.disabled = choice.value === "transfer" && state.targetSport === state.selected.sport;
      input.addEventListener("change", () => {
        if (!input.checked) return;
        state.basis = input.value;
        updateUrl();
        renderResult(`input[name="estimate-basis"][value="${state.basis}"]`);
        announceResult();
      });
      append(option, input, element("strong", "", choice.label), element("small", "", choice.help));
      options.append(option);
    });
    fieldset.append(options);
    const note = element(
      "p",
      "comparison-note",
      state.targetSport === state.selected.sport
        ? "For the athlete's own sport, use their observed result below as the reality check. A playing-style transfer needs a different target sport."
        : "Playing-style comparisons map broad, shared game traits between sports. They do not measure whether the athlete has the target sport's specific skills.",
    );
    return append(section, selectGrid, fieldset, note);
  }

  function statusBadge(score) {
    const info = statusInfo(score);
    return element("span", `friendly-status ${info.className}`.trim(), info.label);
  }

  function scoreCard(score, payload) {
    const label = payload.label || roleLabel(state.targetSport, state.targetRole);
    const card = element("section", "fit-card");
    const heading = element("div", "card-heading");
    append(
      heading,
      element("h3", "", "Estimated fit for this role"),
      statusBadge(score),
    );
    card.append(heading);

    if (!scoreAvailable(score)) {
      append(
        card,
        element("div", "big-score", "No score"),
        element("p", "rank-band", "The model stopped here"),
        element("p", "score-meaning", reasonFor(score)),
        element("p", "plain-warning", "No score shown is not zero. It means this comparison was not reliable enough to display."),
      );
      return card;
    }

    const amount = element("div", "big-score");
    append(amount, document.createTextNode(format(score.value, 1)), element("small", "", "out of 100"));
    const track = element("div", "score-track");
    const fill = element("span");
    fill.style.width = `${clamp(score.value)}%`;
    fill.setAttribute("aria-hidden", "true");
    track.append(fill);
    append(
      card,
      amount,
      element("p", "rank-band", comparisonBand(score.value)),
      element("p", "score-meaning", percentileMeaning(score.value, label)),
      track,
    );

    const predictionRange = score?.prediction_range_90;
    const calibratedRange = predictionRange
      && finite(predictionRange.lower)
      && finite(predictionRange.upper)
      ? [predictionRange.lower, predictionRange.upper]
      : null;
    const sensitivityRange = score.analogy_sensitivity_range;
    const displayedRange = calibratedRange || (
      Array.isArray(sensitivityRange)
      && sensitivityRange.length === 2
      && sensitivityRange.every(finite)
        ? sensitivityRange
        : null
    );
    if (displayedRange) {
      const range = element("div", "rough-range");
      append(
        range,
        element("span", "", calibratedRange ? "90% historical prediction range" : "Rough sensitivity range"),
        element("strong", "", `${format(displayedRange[0])}–${format(displayedRange[1])}`),
        element(
          "small",
          "",
          calibratedRange
            ? "Based on earlier target-role forecast errors—not a sport-switch probability or guarantee."
            : "A stress test around the estimate—not a confidence interval or guarantee.",
        ),
      );
      card.append(range);
      if (calibratedRange && score.interval_calibration_warning) {
        card.append(element("p", "plain-warning", score.interval_calibration_warning));
      }
    }
    if (score.saturation_warning || score.value >= 99.5) {
      card.append(element("p", "plain-warning", "The estimate reached the model's upper limit. This does not mean perfect ability."));
    } else if (String(score.ood?.status || "").includes("warning")) {
      card.append(element("p", "plain-warning", "Part of this athlete's profile is uncommon for the comparison group, so use the number with extra care."));
    }
    return card;
  }

  function buildCard(body, payload) {
    const card = element("section", "build-card");
    const heading = element("div", "card-heading");
    append(heading, element("h3", "", "How typical is this build?"), element("span", "friendly-status", "Height + weight"));
    card.append(heading);
    if (!scoreAvailable(body)) {
      append(
        card,
        element("div", "build-score", "No score"),
        element("p", "build-label", "Build comparison unavailable"),
        element("p", "build-meaning", `${reasonFor(body, "There was not enough body data for this comparison.")} No score is not zero.`),
      );
      return card;
    }

    const amount = element("div", "build-score");
    append(amount, document.createTextNode(format(body.value, 1)), element("small", "", "out of 100"));
    const blocks = element("div", "build-blocks");
    const active = Math.ceil(clamp(body.value) / 10);
    for (let index = 1; index <= 10; index += 1) {
      blocks.append(element("i", index <= active ? "on" : ""));
    }
    blocks.setAttribute("aria-hidden", "true");
    append(
      card,
      amount,
      element("p", "build-label", bodyBand(body.value)),
      blocks,
      element(
        "p",
        "build-meaning",
        `${possessive(state.selected.name)} height and weight are more typical than about ${Math.round(body.value)} of every 100 ${payload.label || roleLabel(state.targetSport, state.targetRole)} profiles. An unusual build is not a judgment of ability.`,
      ),
    );
    return card;
  }

  function whyCard(score, payload) {
    const card = element("section", "why-card");
    card.append(element("h3", "", "Why did the model say that?"));
    const list = element("ul", "why-list");
    explanationSentences(score, payload, state.basis).forEach((sentence, index) => {
      list.append(element("li", !scoreAvailable(score) || (index === 0 && statusInfo(score).className === "caution") ? "caution" : "", sentence));
    });
    card.append(list);
    return card;
  }

  function nativeCard(label, value, note) {
    const card = element("div", "reality-item");
    append(card, element("span", "", label), element("strong", "", value), element("small", "", note));
    return card;
  }

  function realityCheck() {
    const section = element("section", "reality");
    section.append(element("h3", "", "Reality check: what happened in their own sport?"));
    const grid = element("div", "reality-grid");
    const observed = state.detail?.native?.observed;
    const forecast = state.detail?.native?.forecast;
    const sourceRole = roleLabel(state.selected.sport, state.selected.role);
    if (observedAvailable(observed)) {
      grid.append(nativeCard(
        "How they ranked in their own role",
        `${format(observed.value, 1)} / 100`,
        observed.status === "low_sample"
          ? `Higher than about ${Math.round(observed.value)}% of ${sourceRole} players, but based on limited playing time.`
          : `Higher than about ${Math.round(observed.value)}% of ${sourceRole} players in this season.`,
      ));
    } else {
      grid.append(nativeCard("How they ranked in their own role", "—", reasonFor(observed, "No observed result was available.")));
    }

    if (scoreAvailable(forecast)) {
      const forecastRange = forecast.prediction_range_90;
      const rangeNote = finite(forecastRange?.lower) && finite(forecastRange?.upper)
        ? ` Historical 90% range: ${format(forecastRange.lower)}–${format(forecastRange.upper)}; this is not a guarantee.`
        : "";
      grid.append(nativeCard(
        "Next-season outlook",
        `${format(forecast.value, 1)} / 100`,
        `An early model estimate for their own role. It has not yet beaten the project's comparison baselines.${rangeNote}`,
      ));
    } else {
      grid.append(nativeCard("Next-season outlook", "—", reasonFor(forecast, "No next-season outlook was available.")));
    }

    const domains = Array.isArray(state.detail?.native_profile?.domains)
      ? state.detail.native_profile.domains.filter((item) => finite(item?.value))
      : [];
    const strongest = domains.sort((left, right) => right.value - left.value)[0];
    if (strongest) {
      grid.append(nativeCard(
        "Strongest part of their game",
        words(strongest.label),
        `About the ${ordinal(strongest.value)} percentile within their own role.`,
      ));
    } else {
      grid.append(nativeCard("Strongest part of their game", "—", "No comparable playing-style breakdown was available."));
    }
    section.append(grid);
    return section;
  }

  function detailItem(label, value) {
    const item = element("li");
    append(item, element("strong", "", `${label}: `), document.createTextNode(value));
    return item;
  }

  function technicalDetails(score, payload) {
    const details = element("details", "research-details");
    details.append(element("summary", "", "Show the research details"));
    const content = element("div", "detail-content");
    const list = element("ul", "detail-list");
    append(
      list,
      detailItem("Selected basis", state.basis === "transfer" ? "Body + playing style" : "Body + age only"),
      detailItem("Saved status", words(score?.status || "unknown")),
      detailItem("Evidence class", words(score?.evidence_class || "not listed")),
      detailItem("Reference rows", finite(score?.reference_rows) ? format(score.reference_rows) : "Not listed"),
      detailItem("Profile check", words(score?.ood?.status || "not listed")),
      detailItem("Bridge strength", words(score?.semantic_bridge_grade || "not used")),
    );
    const limitation = element("p", "role-note");
    const roleCaveat = payload.limitation || roleConfig(state.targetSport, state.targetRole)?.limitation;
    limitation.textContent = roleCaveat
      ? `Role data note: ${roleCaveat}`
      : "This role uses a public-stat research proxy, not a complete measure of sporting quality.";
    append(content, list, limitation);
    details.append(content);
    return details;
  }

  function renderResult(focusSelector = null) {
    if (!state.selected || !state.detail) return;
    normaliseSelection();
    const payload = selectedPayload();
    if (!payload) {
      const error = element("div", "result-error");
      error.append(element("p", "", "This saved player file does not include that role comparison."));
      result.replaceChildren(error);
      return;
    }
    const score = state.basis === "transfer" ? payload.transfer_guesstimate : payload.physical_only;
    const answer = element("section", "answer");
    const grid = element("div", "answer-grid");
    append(grid, scoreCard(score, payload), buildCard(payload.body_fit, payload));
    append(answer, grid, whyCard(score, payload), realityCheck(), technicalDetails(score, payload));
    result.replaceChildren(athleteHeader(), comparisonControls(), answer);
    result.setAttribute("aria-busy", "false");
    if (focusSelector) result.querySelector(focusSelector)?.focus();
  }

  function announceResult() {
    const payload = selectedPayload();
    if (!payload) return;
    const score = state.basis === "transfer" ? payload.transfer_guesstimate : payload.physical_only;
    const scoreText = scoreAvailable(score) ? `${format(score.value, 1)} out of 100` : "no score shown";
    announcement.textContent = `${state.selected.name}, ${sportLabel(state.targetSport)} ${payload.label}: ${scoreText}.`;
  }

  function loadingResult() {
    const loading = element("div", "loading");
    append(loading, element("span"), element("p", "", "Preparing an easy-to-read comparison…"));
    result.replaceChildren(loading);
    result.setAttribute("aria-busy", "true");
  }

  function resultError(message, player) {
    const wrapper = element("div", "result-error");
    append(wrapper, element("p", "", message));
    const retry = element("button", "retry", "Try loading again");
    retry.type = "button";
    retry.addEventListener("click", () => selectPlayer(player, {}, true));
    wrapper.append(retry);
    result.replaceChildren(wrapper);
    result.setAttribute("aria-busy", "false");
  }

  function playerButton(player) {
    const button = element("button", "player-option");
    button.type = "button";
    button.setAttribute("aria-current", player.id === state.selected?.id ? "true" : "false");
    const copy = element("span", "player-copy");
    const context = [sportLabel(player.sport), player.team, roleLabel(player.sport, player.role)].filter(Boolean).join(" · ");
    append(copy, element("strong", "", player.name), element("small", "", context));
    append(button, element("span", "avatar", initials(player.name)), copy);
    button.addEventListener("click", () => selectPlayer(player));
    return button;
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
    const matches = filteredPlayers();
    playerCount.textContent = format(matches.length);
    if (!matches.length) {
      playerList.replaceChildren(element("p", "empty-state", "No athletes match that search. Try a shorter name or another league."));
      return;
    }
    const shown = matches.slice(0, listLimit);
    if (state.selected && matches.some((player) => player.id === state.selected.id)
      && !shown.some((player) => player.id === state.selected.id)) {
      shown[shown.length - 1] = state.selected;
    }
    const fragment = document.createDocumentFragment();
    shown.forEach((player) => fragment.append(playerButton(player)));
    if (matches.length > listLimit) {
      fragment.append(element("p", "list-limit", `Showing the first ${listLimit} matches. Search by name to narrow the list.`));
    }
    playerList.replaceChildren(fragment);
  }

  async function selectPlayer(player, preferred = {}, isRetry = false) {
    if (!player) return;
    const request = state.request + 1;
    state.request = request;
    state.selected = player;
    state.detail = null;
    if (!isRetry) renderPlayerList();
    loadingResult();
    try {
      const detail = await fetchJson(player.detail_path);
      if (request !== state.request) return;
      state.detail = detail;
      const parameters = new URLSearchParams(window.location.search);
      normaliseSelection({
        sport: preferred.sport || (isRetry ? state.targetSport : parameters.get("sport")),
        role: preferred.role || (isRetry ? state.targetRole : parameters.get("role")),
        basis: preferred.basis || (isRetry ? state.basis : parameters.get("basis")),
      });
      updateUrl();
      renderResult();
      renderPlayerList();
      announceResult();
    } catch (error) {
      if (request !== state.request) return;
      resultError(error instanceof Error ? error.message : "The player result could not be loaded.", player);
    }
  }

  function populateSourceSports() {
    (state.manifest?.sports || []).forEach((sport) => {
      const option = element("option", "", sport.label);
      option.value = sport.id;
      sourceSport.append(option);
    });
  }

  function bindFilters() {
    search.addEventListener("input", () => {
      state.query = search.value;
      renderPlayerList();
    });
    sourceSport.addEventListener("change", () => {
      state.sourceSport = sourceSport.value;
      renderPlayerList();
    });
  }

  function showFatalError(message) {
    appError.hidden = false;
    appError.textContent = `${message} Start a local web server from the project folder, then reload this page.`;
    explorerGrid.setAttribute("aria-busy", "false");
    playerList.replaceChildren(element("p", "empty-state", "The player list could not be loaded."));
    resultError("The saved model results could not be loaded.", null);
    const retry = result.querySelector("button");
    if (retry) retry.remove();
  }

  async function initialise() {
    bindFilters();
    try {
      state.manifest = await fetchJson("manifest.json");
      state.players = Array.isArray(state.manifest.players) ? state.manifest.players : [];
      populateSourceSports();
      const total = state.manifest.counts?.players || state.players.length;
      snapshotNote.textContent = `Saved snapshot with ${format(total)} athletes across the NFL, NBA, NHL, and Premier League.`;
      explorerGrid.setAttribute("aria-busy", "false");
      const parameters = new URLSearchParams(window.location.search);
      const requestedId = parameters.get("player");
      const defaultId = state.manifest.defaults?.player_id;
      const player = state.players.find((item) => item.id === requestedId)
        || (!requestedId && state.players.find((item) => item.id === "nba:3975"))
        || state.players.find((item) => item.id === defaultId)
        || state.players[0];
      renderPlayerList();
      if (!player) throw new Error("The saved player list is empty.");
      const isGuidedDefault = !requestedId && player.id === "nba:3975";
      await selectPlayer(player, {
        sport: parameters.get("sport") || (isGuidedDefault ? "epl" : state.manifest.defaults?.target_sport),
        role: parameters.get("role") || (isGuidedDefault ? "FWD" : null),
        basis: parameters.get("basis") || (isGuidedDefault ? "transfer" : null),
      });
    } catch (error) {
      showFatalError(error instanceof Error ? error.message : "The saved project data could not be read.");
    }
  }

  initialise();
})();
