/* Native-first player profile over the shared all-role export. */
"use strict";

(() => {
  const dataRoot = new URL("../data/", document.baseURI);
  const listLimit = 160;
  const featureNames = {
    height_cm: "height",
    weight_kg: "weight",
    bmi: "height-to-weight balance",
    age: "age",
    observed_role_percentile: "observed home-role result",
    availability_percentile: "availability",
    sustained_3y_percentile: "sustained three-season performance",
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
    not_applicable_without_source_performance: "A playing-profile comparison is only used when the target is a different sport.",
    withheld_no_fitted_model: "There was not enough reliable data to score this role.",
    withheld_missing_height_or_weight: "Height or weight is missing.",
    withheld_missing_fixed_bridge_dimensions: "The source sport does not provide enough comparable playing-profile data.",
    withheld_missing_required_dimensions: "The source sport does not provide enough comparable playing-profile data.",
    withheld_proxy_model_failed_baseline_gate: "This estimate was too unreliable in testing.",
    withheld_target_proxy_reconstruction_failed_gate: "This estimate was too unreliable in testing.",
    withheld_source_performance_not_eligible: "The player did not have enough playing time for a reliable source profile.",
    withheld_out_of_domain: "This athlete is too different from the players used to build this comparison.",
    withheld_insufficient_reference: "Too few players in this role have usable measurements.",
    withheld_same_sport_transfer: "Choose another sport to use the playing-profile comparison.",
    low_sample: "The player did not have enough playing time for a full-strength result.",
    missing: "The information needed for this result is missing.",
    not_observed: "There was not enough season information to show this result.",
    out_of_domain: "This athlete is too different from the comparison group.",
  };

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

  const search = document.querySelector("#player-search");
  const sourceSport = document.querySelector("#source-sport");
  const playerCount = document.querySelector("#player-count");
  const playerList = document.querySelector("#player-list");
  const result = document.querySelector("#result");
  const announcement = document.querySelector("#announcement");
  const appError = document.querySelector("#app-error");
  const profileGrid = document.querySelector("#profile-grid");
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
    return noScoreReasons[score?.reason]
      || noScoreReasons[score?.status]
      || fallback
      || "The model did not have enough familiar evidence to show a responsible number.";
  }

  function performanceBand(value) {
    if (value >= 90) return "Elite home-role season";
    if (value >= 75) return "Strong home-role season";
    if (value >= 60) return "Above-average home-role season";
    if (value >= 40) return "Around the middle of the role";
    if (value >= 25) return "Below the role average";
    return "Lower home-role season";
  }

  function comparisonBand(value) {
    if (value >= 90) return "Top-tier model comparison";
    if (value >= 75) return "Strong model comparison";
    if (value >= 60) return "Above-average model comparison";
    if (value >= 40) return "Around the middle";
    if (value >= 25) return "Below-average model comparison";
    return "Weak model comparison";
  }

  function bodyBand(value) {
    if (value >= 75) return "Very typical build";
    if (value >= 40) return "Fairly typical build";
    if (value >= 15) return "Less typical build";
    return "Very unusual build";
  }

  function measurement(label, value) {
    return append(element("div"), element("dt", "", label), element("dd", "", value));
  }

  function statusChip(label, className = "") {
    return element("span", `status-chip ${className}`.trim(), label);
  }

  function scoreTrack(value, className = "score-track") {
    const track = element("div", className);
    const fill = element("span");
    fill.style.width = `${clamp(value)}%`;
    fill.setAttribute("aria-hidden", "true");
    track.append(fill);
    return track;
  }

  function playerSummary() {
    const player = state.selected;
    const section = element("header", "player-summary panel");
    const top = element("div", "summary-top");
    const name = element("div", "summary-name");
    append(
      name,
      element("span", "avatar", initials(player.name)),
      append(
        element("div"),
        element("p", "eyebrow", "Selected player"),
        element("h2", "", player.name),
      ),
    );
    append(top, name, element("span", "league-label", sportLabel(player.sport)));

    const meta = element("p", "summary-meta");
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

  function stepHeading(number, eyebrow, title, description, badge) {
    const wrapper = element("div", "step-heading");
    const copy = element("div", "step-copy");
    append(
      copy,
      element("span", "step-number", number),
      append(
        element("div"),
        element("p", "eyebrow", eyebrow),
        element("h3", "", title),
        element("p", "", description),
      ),
    );
    append(wrapper, copy, badge);
    return wrapper;
  }

  function evidenceItem(label, value, note) {
    const item = element("div", "evidence-item");
    return append(item, element("span", "", label), element("strong", "", value), element("small", "", note));
  }

  function domainRows() {
    const list = element("div", "domain-list");
    const domains = Array.isArray(state.detail?.native_profile?.domains)
      ? state.detail.native_profile.domains.filter((item) => finite(item?.value))
      : [];
    if (!domains.length) {
      list.append(element("p", "estimate-meaning", "No role-specific playing breakdown was available."));
      return list;
    }
    [...domains]
      .sort((left, right) => right.value - left.value)
      .slice(0, 5)
      .forEach((domain) => {
        const row = element("div", "domain-row");
        const track = element("span", "mini-track");
        const fill = element("i");
        fill.style.width = `${clamp(domain.value)}%`;
        fill.setAttribute("aria-hidden", "true");
        track.append(fill);
        append(row, element("span", "", words(domain.label)), track, element("strong", "", format(domain.value)));
        list.append(row);
      });
    return list;
  }

  function observedAnchor() {
    const observed = state.detail?.native?.observed;
    const role = roleLabel(state.selected.sport, state.selected.role);
    const season = state.selected.season || "Latest";
    const section = element("section", "anchor panel");
    const available = observedAvailable(observed);
    const badge = available
      ? statusChip(observed.status === "low_sample" ? "Limited sample" : "Observed season result", observed.status === "low_sample" ? "caution" : "")
      : statusChip("Observed result unavailable", "unavailable");
    section.append(stepHeading(
      "1",
      "Home-role anchor",
      "What has this player already shown?",
      "This descriptive score comes before every forecast or role comparison because it reflects actual performance in the player's own setting.",
      badge,
    ));

    const grid = element("div", "anchor-grid");
    const score = element("div", "native-score");
    score.append(element("p", "score-context", `${season} · ${sportLabel(state.selected.sport)} · ${role}`));
    if (available) {
      const value = element("div", "score-value");
      append(value, document.createTextNode(format(observed.value, 1)), element("small", "", "out of 100"));
      append(
        score,
        value,
        element("p", "score-band", performanceBand(observed.value)),
        element("p", "score-explanation", `The season result was higher than about ${Math.round(observed.value)} of every 100 players in the ${role} comparison group.`),
        scoreTrack(observed.value),
        element(
          "p",
          "anchor-note",
          observed.status === "low_sample"
            ? "This is an observed result, but the playing-time sample was too small for full-strength model training. It does not validate the models shown later."
            : "This is a retrospective season percentile—not a prediction, a percentage chance of success, or validation of the models shown later.",
        ),
      );
    } else {
      append(
        score,
        element("div", "score-value", "No score"),
        element("p", "score-band", "The data stopped here"),
        element("p", "score-explanation", reasonFor(observed, "No observed home-role result was available.")),
        element("p", "anchor-note", "No score is not zero. It means the project could not make a responsible comparison."),
      );
    }

    const evidence = element("div", "native-evidence");
    evidence.append(element("h4", "", "The season behind the headline"));
    const metrics = element("div", "evidence-grid");
    if (available) {
      append(
        metrics,
        evidenceItem("Quality", `${format(observed.quality_percentile ?? observed.value, 1)} / 100`, "Role-specific performance components."),
        evidenceItem("Availability", `${format(observed.availability_percentile, 1)} / 100`, "Opportunity and time available to contribute."),
        evidenceItem("Total impact", `${format(observed.total_impact_percentile ?? observed.value, 1)} / 100`, "Quality combined with availability."),
        evidenceItem("Sustained form", finite(observed.sustained_3y_percentile) ? `${format(observed.sustained_3y_percentile, 1)} / 100` : "—", "Up to three seasons of role-relative performance."),
        evidenceItem("Comparison group", finite(observed.reference_athletes) ? format(observed.reference_athletes) : "—", "Athletes in the same role-season reference group."),
      );
    } else {
      metrics.append(evidenceItem("Observed evidence", "Unavailable", "See the data note for why the score was withheld."));
    }
    append(evidence, metrics, element("h4", "", "Role-relative playing profile"), domainRows());
    append(grid, score, evidence);
    section.append(grid);
    return section;
  }

  function contributionSentence(contribution) {
    const feature = featureNames[contribution?.feature] || words(contribution?.feature).toLowerCase();
    if (!finite(contribution?.contribution)) return `The model included ${feature}.`;
    return contribution.contribution >= 0
      ? `${words(feature)} pushed the outlook upward.`
      : `${words(feature)} pulled the outlook toward the middle.`;
  }

  function forecastSection() {
    const forecast = state.detail?.native?.forecast;
    const observed = state.detail?.native?.observed;
    const section = element("section", "forecast panel");
    const available = scoreAvailable(forecast);
    section.append(stepHeading(
      "2",
      "Same sport, next season",
      "What does the native model estimate next?",
      "This forecast uses prior seasons and the player's home-role profile. It is deliberately shown after the observed result.",
      available ? statusChip("Experimental forecast", "caution") : statusChip("Forecast unavailable", "unavailable"),
    ));

    const body = element("div", "forecast-body");
    const amount = element("div", "forecast-score");
    if (available) {
      append(
        amount,
        element("strong", "", `${format(forecast.value, 1)} / 100`),
        element("span", "", `${forecast.target_season || "Next season"} ${roleLabel(state.selected.sport, state.selected.role)} outlook`),
      );
    } else {
      append(amount, element("strong", "", "—"), element("span", "", "No next-season forecast shown"));
    }

    const copy = element("div", "forecast-copy");
    if (available) {
      let relationship = "The observed and forecast results answer different questions.";
      if (observedAvailable(observed)) {
        const difference = forecast.value - observed.value;
        if (Math.abs(difference) < 1) {
          relationship = "The forecast is close to the observed season result.";
        } else {
          relationship = `The forecast is ${format(Math.abs(difference), 1)} points ${difference > 0 ? "above" : "below"} the observed season result.`;
        }
      }
      append(
        copy,
        element("p", "", relationship),
        element("p", "", forecast.evidence_warning || "This estimate is experimental and should be checked against future seasons."),
      );
      const contributions = Array.isArray(forecast.top_contributions)
        ? forecast.top_contributions.filter((item) => item?.feature).slice(0, 3)
        : [];
      if (contributions.length) {
        copy.append(element("strong", "", "Main signals used"));
        const list = element("ul", "contribution-list");
        contributions.forEach((item) => list.append(element("li", "", contributionSentence(item))));
        copy.append(list);
      }
    } else {
      copy.append(element("p", "", `${reasonFor(forecast, "No native forecast was available.")} The observed score above can still be read on its own.`));
    }
    append(body, amount, copy);
    section.append(body);
    return section;
  }

  function availableTargetSports() {
    const targets = state.detail?.targets || {};
    const ordered = (state.manifest?.sports || []).filter((sport) => targets[sport.id]);
    Object.keys(targets).forEach((id) => {
      if (!ordered.some((sport) => sport.id === id)) ordered.push({ id, label: sportLabel(id), roles: [] });
    });
    return ordered;
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

  function chooseRole(sport, preferred) {
    const roles = orderedRoles(sport);
    if (roles.some((role) => role.id === preferred)) return preferred;
    if (sport === state.selected?.sport && roles.some((role) => role.id === state.selected?.role)) {
      return state.selected.role;
    }
    return roles[0]?.id || null;
  }

  function normaliseSelection(preferred = {}) {
    const sports = availableTargetSports();
    const requestedSport = preferred.sport || state.targetSport || state.selected?.sport;
    state.targetSport = sports.some((sport) => sport.id === requestedSport)
      ? requestedSport
      : sports.find((sport) => sport.id === state.selected?.sport)?.id || sports[0]?.id || null;
    state.targetRole = chooseRole(state.targetSport, preferred.role || state.targetRole);
    const requestedBasis = preferred.basis || state.basis;
    state.basis = requestedBasis === "transfer" || requestedBasis === "physical" ? requestedBasis : "physical";
    if (state.targetSport === state.selected?.sport) state.basis = "physical";
  }

  function selectedPayload() {
    return state.detail?.targets?.[state.targetSport]?.roles?.[state.targetRole] || null;
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

  function comparisonStatus(score) {
    if (!scoreAvailable(score)) return statusChip("No score shown", "unavailable");
    if (score.support_status === "association_gate_supported") return statusChip("Passed internal gate");
    return statusChip("Experimental", "caution");
  }

  function comparisonControls() {
    const wrapper = element("div", "comparison-controls");
    const selectGrid = element("div", "select-grid");

    const sportWrap = element("div");
    const sportLabelElement = element("label", "", "Sport to compare with");
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
      const wasSameSport = state.targetSport === state.selected.sport;
      state.targetSport = sportSelect.value;
      state.targetRole = chooseRole(state.targetSport, null);
      if (state.targetSport === state.selected.sport) state.basis = "physical";
      else if (wasSameSport) state.basis = "transfer";
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
    fieldset.append(element("legend", "", "Which secondary model should be shown?"));
    const options = element("div", "basis-options");
    [
      { value: "transfer", label: "Build + playing profile", help: "Broad cross-sport analogy." },
      { value: "physical", label: "Build + age only", help: "Physical association model." },
    ].forEach((choice) => {
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
        ? "This same-sport physical estimate answers a narrower question than the observed score above. It does not re-grade the player's season."
        : "Cross-sport estimates compare broad profiles. They do not measure learned technique, tactical knowledge, or the probability of making a roster.",
    );
    return append(wrapper, selectGrid, fieldset, note);
  }

  function estimateCard(score, payload) {
    const card = element("section", "estimate-card");
    const heading = element("div", "card-heading");
    append(
      heading,
      element("h4", "", state.basis === "transfer" ? "Build + playing-profile analogy" : "Build-linked estimate"),
      comparisonStatus(score),
    );
    card.append(heading);
    if (!scoreAvailable(score)) {
      append(
        card,
        element("div", "estimate-value", "No score"),
        element("p", "estimate-band", "The secondary model stopped here"),
        element("p", "estimate-meaning", reasonFor(score)),
        element("p", "secondary-warning", "No score is not zero. The observed home-role result above is unaffected."),
      );
      return card;
    }

    const amount = element("div", "estimate-value");
    append(amount, document.createTextNode(format(score.value, 1)), element("small", "", "out of 100"));
    const target = `${sportLabel(state.targetSport)} ${payload.label || roleLabel(state.targetSport, state.targetRole)}`;
    append(
      card,
      amount,
      element("p", "estimate-band", comparisonBand(score.value)),
      element(
        "p",
        "estimate-meaning",
        state.basis === "transfer"
          ? `The analogy places this player's build and broad playing profile near the ${format(score.value)}th percentile for ${target}.`
          : `The physical association model places this height, weight, age, and BMI profile near the ${format(score.value)}th percentile for ${target}.`,
      ),
      scoreTrack(score.value),
    );

    const reasons = Array.isArray(score.top_contributions)
      ? score.top_contributions.filter((item) => item?.feature).slice(0, 2)
      : [];
    if (reasons.length) {
      const list = element("ul", "reason-list");
      reasons.forEach((item) => list.append(element("li", "", contributionSentence(item))));
      card.append(list);
    }
    card.append(element(
      "p",
      "secondary-warning",
      state.targetSport === state.selected.sport
        ? "This model value can differ sharply from the observed score because it mainly asks whether physical traits were associated with target-role performance in the training data."
        : "This is an exploratory analogy, not a sport-switch probability or a validated outcome forecast.",
    ));
    return card;
  }

  function bodyCard(body, payload) {
    const card = element("section", "body-card");
    const heading = element("div", "card-heading");
    append(heading, element("h4", "", "Body typicality"), statusChip("Descriptive"));
    card.append(heading);
    if (!scoreAvailable(body)) {
      append(
        card,
        element("div", "body-value", "No score"),
        element("p", "body-band", "Body comparison unavailable"),
        element("p", "body-meaning", `${reasonFor(body, "There was not enough body data for this role.")} No score is not zero.`),
      );
      return card;
    }
    const amount = element("div", "body-value");
    append(amount, document.createTextNode(format(body.value, 1)), element("small", "", "out of 100"));
    append(
      card,
      amount,
      element("p", "body-band", bodyBand(body.value)),
      element("p", "body-meaning", `This build is more typical than about ${Math.round(body.value)} of every 100 ${payload.label || roleLabel(state.targetSport, state.targetRole)} profiles. Typical does not mean better.`),
    );
    return card;
  }

  function detailItem(label, value) {
    return append(element("li"), element("strong", "", `${label}: `), document.createTextNode(value));
  }

  function researchDetails(score, payload) {
    const details = element("details", "research-details");
    details.append(element("summary", "", "Show model evidence details"));
    const list = element("ul", "detail-list");
    append(
      list,
      detailItem("Selected basis", state.basis === "transfer" ? "Build + playing profile" : "Build + age only"),
      detailItem("Saved status", words(score?.status || "unknown")),
      detailItem("Evidence class", words(score?.evidence_class || "not listed")),
      detailItem("Reference rows", finite(score?.reference_rows) ? format(score.reference_rows) : "Not listed"),
      detailItem("Profile check", words(score?.ood?.status || "not listed")),
      detailItem("Role data note", payload.limitation || "Public-stat research proxy; not a complete measure of player quality."),
    );
    details.append(list);
    return details;
  }

  function comparisonSection() {
    const section = element("section", "comparison panel");
    section.append(stepHeading(
      "3",
      "Secondary models",
      "Now explore other roles",
      "Only after reading the home-role result should the physical and cross-sport models be used to form new questions.",
      statusChip("Exploratory", "caution"),
    ));
    section.append(comparisonControls());
    const payload = selectedPayload();
    if (!payload) {
      section.append(element("p", "secondary-warning", "This saved player file does not include that role comparison."));
      return section;
    }
    const score = state.basis === "transfer" ? payload.transfer_guesstimate : payload.physical_only;
    const grid = element("div", "comparison-grid");
    append(grid, estimateCard(score, payload), bodyCard(payload.body_fit, payload));
    append(section, grid, researchDetails(score, payload));
    return section;
  }

  function renderResult(focusSelector = null) {
    if (!state.selected || !state.detail) return;
    normaliseSelection();
    result.replaceChildren(playerSummary(), observedAnchor(), forecastSection(), comparisonSection());
    result.setAttribute("aria-busy", "false");
    if (focusSelector) result.querySelector(focusSelector)?.focus();
  }

  function announceResult() {
    const observed = state.detail?.native?.observed;
    const observedText = observedAvailable(observed) ? `${format(observed.value, 1)} out of 100 observed` : "no observed score shown";
    const payload = selectedPayload();
    const score = state.basis === "transfer" ? payload?.transfer_guesstimate : payload?.physical_only;
    const comparisonText = scoreAvailable(score) ? `${format(score.value, 1)} out of 100 secondary estimate` : "no secondary estimate shown";
    announcement.textContent = `${state.selected.name}: ${observedText}; ${comparisonText}.`;
  }

  function loadingResult() {
    const loading = element("div", "loading panel");
    append(loading, element("span"), element("p", "", "Building the player profile…"));
    result.replaceChildren(loading);
    result.setAttribute("aria-busy", "true");
  }

  function resultError(message, player) {
    const wrapper = element("div", "result-error panel");
    append(wrapper, element("p", "", message));
    if (player) {
      const retry = element("button", "retry", "Try loading again");
      retry.type = "button";
      retry.addEventListener("click", () => selectPlayer(player, {}, true));
      wrapper.append(retry);
    }
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
    button.addEventListener("click", () => selectPlayer(player, { sport: player.sport, role: player.role, basis: "physical" }));
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
      normaliseSelection({
        sport: preferred.sport || (isRetry ? state.targetSport : player.sport),
        role: preferred.role || (isRetry ? state.targetRole : player.role),
        basis: preferred.basis || (isRetry ? state.basis : "physical"),
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
    profileGrid.setAttribute("aria-busy", "false");
    playerList.replaceChildren(element("p", "empty-state", "The player list could not be loaded."));
    resultError("The saved model results could not be loaded.", null);
  }

  async function initialise() {
    bindFilters();
    try {
      state.manifest = await fetchJson("manifest.json");
      state.players = Array.isArray(state.manifest.players) ? state.manifest.players : [];
      populateSourceSports();
      const total = state.manifest.counts?.players || state.players.length;
      snapshotNote.textContent = `Saved snapshot with ${format(total)} athletes across the NFL, NBA, NHL, and Premier League.`;
      profileGrid.setAttribute("aria-busy", "false");
      const parameters = new URLSearchParams(window.location.search);
      const requestedId = parameters.get("player");
      const defaultId = state.manifest.defaults?.player_id;
      const player = state.players.find((item) => item.id === requestedId)
        || (!requestedId && state.players.find((item) => item.id === "nhl:8478402"))
        || state.players.find((item) => item.id === defaultId)
        || state.players[0];
      renderPlayerList();
      if (!player) throw new Error("The saved player list is empty.");
      await selectPlayer(player, {
        sport: parameters.get("sport") || player.sport,
        role: parameters.get("role") || player.role,
        basis: parameters.get("basis") || "physical",
      });
    } catch (error) {
      showFatalError(error instanceof Error ? error.message : "The saved project data could not be read.");
    }
  }

  initialise();
})();
