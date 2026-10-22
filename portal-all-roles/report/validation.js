"use strict";

(() => {
  const state = { payload: null, sport: "nfl" };
  const validationSeason = document.querySelector("#validation-season");
  const physicalHeads = document.querySelector("#physical-heads");
  const nativeHeads = document.querySelector("#native-heads");
  const profileHeads = document.querySelector("#profile-heads");
  const bridgeHeads = document.querySelector("#bridge-heads");
  const validationVersion = document.querySelector("#validation-version");
  const validationError = document.querySelector("#validation-error");
  const trainingCohortSummary = document.querySelector("#training-cohort-summary");
  const tabs = document.querySelector("#validation-sport-tabs");
  const sportVerdict = document.querySelector("#sport-verdict");
  const nativeResults = document.querySelector("#native-results");
  const physicalResults = document.querySelector("#physical-results");
  const profileResults = document.querySelector("#profile-results");
  const bridgeDesignNote = document.querySelector("#bridge-design-note");
  const bridgeSummary = document.querySelector("#bridge-summary");
  const ensembleMethod = document.querySelector("#ensemble-method");
  const ensembleResults = document.querySelector("#ensemble-results");
  const ensembleLimitations = document.querySelector("#ensemble-limitations");

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

  function number(value, digits = 1) {
    return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
  }

  function evidence(row) {
    if (row.evidence_gate === "supported") return { label: "Supported research check", style: "supported" };
    if (String(row.status).startsWith("abstain")) return { label: "No public label", style: "withheld" };
    if (row.status === "not_fit") return { label: "Not fitted", style: "withheld" };
    if (row.evidence_gate === "insufficient_frozen_evidence") return { label: "Too little test evidence", style: "caution" };
    return { label: "Experimental / unsupported", style: "caution" };
  }

  function tableCell(value, className = "") {
    return element("td", className, value);
  }

  function modelRow(row) {
    const tr = element("tr");
    const verdict = evidence(row);
    const badge = element("span", `evidence-badge ${verdict.style}`, verdict.label);
    const evidenceCell = element("td");
    evidenceCell.append(badge);
    append(
      tr,
      tableCell(words(row.role), "role-cell"),
      tableCell(row.test_n ?? "—"),
      tableCell(number(row.mae)),
      tableCell(number(row.baseline_mae)),
      tableCell(number(row.spearman, 2)),
      evidenceCell,
    );
    return tr;
  }

  function renderModelRows(target, rows) {
    target.replaceChildren(...rows.map(modelRow));
  }

  function bridgeCopy(design) {
    if (design === "forward_profile_vs_build") {
      return {
        note: "For each exact shared-profile contract, prior-season build plus profile must improve prediction of the target role's next season over build alone. This is a forward test inside the target sport, not cross-sport validation.",
        card: "fitted source-role heads passed the forward profile-over-build gate",
      };
    }
    return {
      note: "This older saved artifact checks same-season target-role reconstruction. It does not yet contain the stricter next-season profile-over-build test, and it is not cross-sport validation.",
      card: "fitted source-role heads passed the older reconstruction gate",
    };
  }

  function bridgeCard(role, summary, copy) {
    const card = element("article", "bridge-card");
    const supported = `${summary.supported} of ${summary.heads}`;
    append(
      card,
      element("h4", "", words(role)),
      element("strong", "", supported),
      element("p", "", copy.card),
      element("small", "", `${summary.candidates} candidate pairings · median held-out MAE ${number(summary.median_test_mae)}`),
    );
    return card;
  }

  function renderSport() {
    const sport = state.payload.all_roles.sports.find((item) => item.id === state.sport);
    if (!sport) return;
    tabs.querySelectorAll("button").forEach((button) => {
      const selected = button.dataset.sport === state.sport;
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
    });
    const profileRows = sport.native_profile || [];
    const nativeSupported = sport.native.filter((row) => row.evidence_gate === "supported").length;
    const physicalSupported = sport.physical.filter((row) => row.evidence_gate === "supported").length;
    const profileSupported = profileRows.filter((row) => row.evidence_gate === "supported").length;
    sportVerdict.textContent = `${sport.label}: ${nativeSupported} of ${sport.native.length} native heads, ${profileSupported} of ${profileRows.length} build-plus-profile heads, and ${physicalSupported} of ${sport.physical.length} physical heads passed their saved evidence gate. A failed gate means the estimate stays experimental or is withheld; it is not a judgment that the athlete lacks ability.`;
    renderModelRows(nativeResults, sport.native);
    renderModelRows(physicalResults, sport.physical);
    renderModelRows(profileResults, profileRows);
    const copy = bridgeCopy(sport.bridge.evidence_design);
    bridgeDesignNote.textContent = copy.note;
    bridgeSummary.replaceChildren(
      ...Object.entries(sport.bridge.target_roles).map(([role, summary]) => bridgeCard(role, summary, copy)),
    );
  }

  function renderTabs() {
    tabs.replaceChildren();
    state.payload.all_roles.sports.forEach((sport) => {
      const button = element("button", "report-tab", sport.label);
      button.type = "button";
      button.role = "tab";
      button.dataset.sport = sport.id;
      button.addEventListener("click", () => {
        state.sport = sport.id;
        renderSport();
      });
      tabs.append(button);
    });
    renderSport();
  }

  function ensembleStatus(head) {
    if (head.status === "evidence_supported") return { label: "Provisional point gate", style: "supported" };
    if (head.status === "insufficient_support") return { label: "Insufficient training support", style: "withheld" };
    return { label: "No primary evidence", style: "caution" };
  }

  function ensembleRow(head) {
    const tr = element("tr");
    const verdict = ensembleStatus(head);
    const statusCell = element("td");
    statusCell.append(element("span", `evidence-badge ${verdict.style}`, verdict.label));
    const improvement = typeof head.relative_mse_improvement === "number"
      ? `${head.relative_mse_improvement >= 0 ? "+" : ""}${(head.relative_mse_improvement * 100).toFixed(1)}%`
      : "—";
    append(
      tr,
      tableCell(head.key, "role-cell"),
      tableCell(head.test_athletes ?? "—"),
      tableCell(words(head.selected_method || "not fitted")),
      tableCell(improvement),
      tableCell(number(head.spearman, 2)),
      statusCell,
    );
    return tr;
  }

  function renderEnsemble() {
    const ensemble = state.payload.ensemble;
    ensembleMethod.textContent = `${ensemble.title} · ${ensemble.version}. ${ensemble.split} It uses ${ensemble.features.map(words).join(" and ")} as learned inputs. This is not the model family used for the broad player-profile bridge above.`;
    ensembleResults.replaceChildren(...ensemble.heads.map(ensembleRow));
    ensembleLimitations.replaceChildren(
      ...ensemble.known_limitations.map((limitation) => {
        const card = element("article", "card");
        return append(card, element("h3", "", "Evidence boundary"), element("p", "", limitation));
      }),
    );
  }

  async function initialise() {
    try {
      const response = await fetch("data/validation.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`Validation data returned ${response.status}.`);
      state.payload = await response.json();
      const allRoles = state.payload.all_roles;
      validationSeason.textContent = allRoles.frozen_test_season;
      physicalHeads.textContent = allRoles.counts.physical_heads_fit;
      nativeHeads.textContent = allRoles.counts.native_heads_fit;
      profileHeads.textContent = allRoles.counts.native_profile_heads_fit ?? 0;
      bridgeHeads.textContent = allRoles.counts.bridge_heads_fit;
      trainingCohortSummary.textContent = allRoles.claims.training_cohort;
      validationVersion.textContent = `All-role schema ${allRoles.schema_version}; target ${allRoles.target_version}; bridge ${allRoles.bridge_version}. “Supported” is a saved research gate, not deployment approval.`;
      renderTabs();
      renderEnsemble();
    } catch (problem) {
      validationError.hidden = false;
      validationError.textContent = `${problem.message} Run the aggregate report export, then reload this page.`;
    }
  }

  initialise();
})();
