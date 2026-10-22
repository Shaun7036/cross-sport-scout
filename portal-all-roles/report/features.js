"use strict";

(() => {
  const state = { payload: null, sport: "nfl" };
  const roleCount = document.querySelector("#role-count");
  const dimensionCount = document.querySelector("#dimension-count");
  const testSeason = document.querySelector("#feature-test-season");
  const version = document.querySelector("#feature-version");
  const error = document.querySelector("#feature-error");
  const dimensions = document.querySelector("#dimension-grid");
  const tabs = document.querySelector("#feature-sport-tabs");
  const roleSummary = document.querySelector("#role-summary");
  const roleList = document.querySelector("#role-list");
  const weightingStatus = document.querySelector("#weighting-status");
  const weightingFields = document.querySelector("#weighting-fields");
  const pairWeighting = document.querySelector("#pair-weighting");
  const boundaries = document.querySelector("#feature-boundaries");

  function element(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = String(text);
    return item;
  }

  function append(parent, ...children) {
    children.filter(Boolean).forEach((child) => parent.append(child));
    return parent;
  }

  function words(value) {
    return String(value || "")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function percent(value) {
    return `${Math.round(Number(value || 0) * 100)}%`;
  }

  function opportunity(role) {
    if (!role.domains.length) return "No public performance label";
    const amount = Number(role.minimum_opportunity).toLocaleString("en-US");
    return `At least ${amount} ${role.opportunity_unit}`;
  }

  function renderDimensions() {
    dimensions.replaceChildren();
    state.payload.dimensions.forEach((dimension, index) => {
      const card = element("article", "dimension-card");
      append(
        card,
        element("span", "dimension-number", String(index + 1).padStart(2, "0")),
        element("h3", "", dimension.label),
        element("p", "", dimension.description),
      );
      dimensions.append(card);
    });
  }

  function metricRow(metric) {
    const item = element("li", "metric-row");
    const copy = element("div");
    append(copy, element("strong", "", metric.label), element("small", "", metric.direction));
    append(item, copy, element("span", "metric-weight", `${percent(metric.weight)} of domain`));
    return item;
  }

  function domainCard(domain) {
    const card = element("section", "domain-card");
    const heading = element("div", "domain-heading");
    const title = element("div");
    append(title, element("h4", "", domain.label), element("p", "", domain.dimension_label));
    append(heading, title, element("span", "domain-weight", `${percent(domain.weight)} of role score`));
    const list = element("ul", "metric-list");
    domain.metrics.forEach((metric) => list.append(metricRow(metric)));
    return append(card, heading, list);
  }

  function roleCard(role) {
    const details = element("details", "role-card");
    const summary = element("summary");
    const copy = element("span", "role-title");
    append(copy, element("strong", "", role.label), element("small", "", opportunity(role)));
    append(summary, copy, element("span", "role-domain-count", role.domains.length ? `${role.domains.length} domains` : "Abstains"));
    details.append(summary);
    const body = element("div", "role-card-body");
    if (!role.domains.length) {
      append(
        body,
        element("p", "role-limitation", role.limitation),
        element("p", "plain-note", "The athlete can remain in the roster and build dataset without receiving a fabricated performance score."),
      );
    } else {
      const grid = element("div", "role-domain-grid");
      role.domains.forEach((domain) => grid.append(domainCard(domain)));
      append(body, grid, element("p", "role-limitation", role.limitation));
    }
    details.append(body);
    return details;
  }

  function renderRoles() {
    const sport = state.payload.sports.find((item) => item.id === state.sport);
    if (!sport) return;
    tabs.querySelectorAll("button").forEach((button) => {
      const selected = button.dataset.sport === state.sport;
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
    });
    const scored = sport.roles.filter((role) => role.domains.length).length;
    roleSummary.textContent = `${sport.label}: ${sport.roles.length} registered roles; ${scored} have a public-stat performance definition. ${sport.source_scope}`;
    roleList.replaceChildren(...sport.roles.map(roleCard));
  }

  function renderTabs() {
    tabs.replaceChildren();
    state.payload.sports.forEach((sport) => {
      const button = element("button", "report-tab", sport.label);
      button.type = "button";
      button.role = "tab";
      button.dataset.sport = sport.id;
      button.addEventListener("click", () => {
        state.sport = sport.id;
        renderRoles();
      });
      tabs.append(button);
    });
    renderRoles();
  }

  function renderBoundaries() {
    boundaries.replaceChildren();
    state.payload.boundaries.forEach((boundary) => {
      const card = element("article", "card");
      append(card, element("h3", "", "What this protects against"), element("p", "", boundary));
      boundaries.append(card);
    });
  }

  function renderWeighting() {
    const weighting = state.payload.reliability_weighting;
    const saved = weighting.status === "saved_in_current_artifact";
    weightingStatus.textContent = saved
      ? `Saved model rule: ${weighting.training_cohort_claim}`
      : `The saved evaluation predates reliability-weighted training and still says: ${weighting.training_cohort_claim} Rebuild the model artifacts before presenting the weighted method as a completed result.`;
    weightingFields.replaceChildren(
      ...weighting.fields.map((field, index) => {
        const card = element("article", "dimension-card");
        return append(
          card,
          element("span", "dimension-number", String(index + 1).padStart(2, "0")),
          element("h3", "", field.label),
          element("p", "", field.description),
          element("p", "plain-formula", field.formula),
        );
      }),
    );
    pairWeighting.textContent = weighting.next_season_pair;
  }

  async function initialise() {
    try {
      const response = await fetch("data/features.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`Feature data returned ${response.status}.`);
      state.payload = await response.json();
      roleCount.textContent = state.payload.role_count.toLocaleString("en-US");
      dimensionCount.textContent = state.payload.dimensions.length.toLocaleString("en-US");
      testSeason.textContent = state.payload.registry.frozen_test_season;
      version.textContent = `Role taxonomy ${state.payload.registry.role_taxonomy_version}; target ${state.payload.registry.target_version}; bridge ${state.payload.registry.bridge_version}.`;
      renderDimensions();
      renderTabs();
      renderWeighting();
      renderBoundaries();
    } catch (problem) {
      error.hidden = false;
      error.textContent = `${problem.message} Run the aggregate report export, then reload this page.`;
    }
  }

  initialise();
})();
