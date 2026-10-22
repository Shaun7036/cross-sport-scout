/* Guided, plain-language stories over the shared all-role export. */
"use strict";

(() => {
  const dataRoot = new URL("../data/", document.baseURI);
  const storyList = document.querySelector("#story-list");
  const storyConfig = [
    {
      playerId: "nhl:8478402",
      target: { sport: "nba", role: "guard" },
      basis: "transfer",
      editorial: {
        category: "Playing profile carries the result",
        hook: "Elite creation and scoring produce a huge comparison—even before we ask whether the sports truly translate.",
        lesson: "This is a useful opening case because the player is elite in his real role, his build is reasonably common in the target role, and his strongest playing traits point in the same direction.",
      },
    },
    {
      playerId: "nba:3975",
      target: { sport: "epl", role: "FWD" },
      basis: "transfer",
      editorial: {
        category: "A balanced match",
        hook: "A familiar scoring profile and a fairly typical build agree on the same result.",
        lesson: "When the build comparison and playing-profile comparison both look strong, the result is easier to understand—but it is still an analogy, not a prediction of an actual sport switch.",
      },
    },
    {
      playerId: "nfl:00-0034796",
      target: { sport: "nhl", role: "left_wing" },
      basis: "transfer",
      editorial: {
        category: "Playing style changes the picture",
        hook: "His mapped scoring and creation profile produces a strong left-wing comparison across two very different sports.",
        lesson: "This case shows how the project looks beyond height and weight. The result is driven by what the athlete has demonstrated in competition—but that translation remains experimental.",
      },
    },
    {
      playerId: "epl:fpl:223094",
      target: { sport: "nfl", role: "WR" },
      basis: "transfer",
      editorial: {
        category: "Strong analogy, unusual build",
        hook: "The performance comparison is very high even though this is an uncommon build for the target role.",
        lesson: "A high cross-sport score and a low build-similarity score are not contradictory. They answer different questions, and the gap between them is exactly what makes this case informative.",
      },
    },
    {
      playerId: "epl:fpl:97032",
      target: { sport: "nba", role: "guard" },
      basis: "transfer",
      editorial: {
        category: "Build alone is not the answer",
        hook: "The body shape is highly typical for the target role, but the overall comparison is more measured.",
        lesson: "Looking the part physically does not automatically create an elite role match. The mapped playing profile still matters, and body similarity is never an ability grade.",
      },
    },
    {
      playerId: "nba:5104157",
      target: { sport: "nfl", role: "WR" },
      basis: "transfer",
      editorial: {
        category: "When the model stops",
        hook: "An exceptional athlete can be so physically unusual that showing a number would be less honest than saying, “We don’t know.”",
        lesson: "Responsible models need limits. Elite performance in one sport is not permission to extrapolate far beyond the players used to build another sport’s comparison.",
      },
    },
  ];

  const featureNames = {
    height_cm: "height",
    weight_kg: "weight",
    bmi: "height-to-weight balance",
    age: "age",
    observed_role_percentile: "recent performance in their own role",
    availability_percentile: "availability",
    sustained_3y_percentile: "sustained performance over three seasons",
    dimension_scoring_finishing_percentile: "scoring and finishing",
    dimension_creation_distribution_percentile: "creation and distribution",
    dimension_possession_security_percentile: "possession security",
    dimension_defensive_disruption_percentile: "defensive disruption",
    dimension_progression_territory_percentile: "progression and territory gain",
    dimension_discipline_efficiency_percentile: "discipline and efficiency",
  };

  const noScoreReasons = {
    not_applicable_without_source_performance: "A cross-sport comparison needs a different source sport.",
    withheld_no_fitted_model: "There was not enough reliable data to score this role.",
    withheld_missing_height_or_weight: "A usable height or weight is missing.",
    withheld_missing_fixed_bridge_dimensions: "The source sport does not provide enough comparable playing-style data.",
    withheld_missing_required_dimensions: "The source sport does not provide enough comparable playing-style data.",
    withheld_proxy_model_failed_baseline_gate: "This estimate was too unreliable in testing.",
    withheld_target_proxy_reconstruction_failed_gate: "This estimate was too unreliable in testing.",
    withheld_target_role_forward_profile_failed_gate: "This estimate was too unreliable in forward testing.",
    withheld_source_performance_not_eligible: "The source season did not have enough playing time for a reliable profile.",
    withheld_out_of_domain: "This athlete is too different from the players used for this comparison.",
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

  async function fetchJson(path) {
    const relative = String(path).replace(/^data\//, "");
    const url = new URL(relative, dataRoot);
    if (url.origin !== window.location.origin || !url.pathname.startsWith(dataRoot.pathname)) {
      throw new Error("The requested file is outside this local project.");
    }
    const response = await fetch(url, { cache: "no-store", credentials: "same-origin" });
    if (!response.ok) throw new Error(`The saved result could not be read (${response.status}).`);
    return response.json();
  }

  function roleLabel(manifest, sport, role) {
    return manifest.sports
      ?.find((item) => item.id === sport)
      ?.roles?.find((item) => item.id === role)?.label || words(role);
  }

  function sportLabel(manifest, sport) {
    return manifest.sports?.find((item) => item.id === sport)?.label || String(sport).toUpperCase();
  }

  function comparisonBand(value) {
    if (value >= 90) return "Top-tier comparison";
    if (value >= 75) return "Strong comparison";
    if (value >= 60) return "Above-average comparison";
    if (value >= 40) return "Near the middle";
    if (value >= 25) return "Below-average comparison";
    return "Weak comparison";
  }

  function bodyBand(value) {
    if (value >= 75) return "Very typical build";
    if (value >= 40) return "Fairly typical build";
    if (value >= 15) return "Less typical build";
    return "Unusual build";
  }

  function scoreBox(label, value, note, options = {}) {
    const box = element("section", `score-box${options.noScore ? " no-score" : ""}`);
    box.append(element("span", "", label));
    const amount = element("div", "score-value", options.noScore ? "No score shown" : format(value, 1));
    if (!options.noScore) amount.append(element("small", "", "out of 100"));
    append(box, amount, element("p", "", note));
    return box;
  }

  function contributionSentence(contribution) {
    const label = featureNames[contribution.feature] || words(contribution.feature).toLocaleLowerCase();
    if (!finite(contribution.contribution)) return `${words(label)} was included in the comparison.`;
    if (contribution.contribution >= 0) return `Their ${label} pushed the comparison higher.`;
    return `Their ${label} pulled the comparison lower.`;
  }

  function bodyReason(body) {
    if (body?.status !== "available" || !finite(body.value)) {
      return "The saved height and weight were not complete enough to support the build comparison.";
    }
    if (body.value < 15) {
      return "Their height and weight are very unusual for this role, so the model avoids guessing beyond familiar examples.";
    }
    if (body.value < 40) return "Their height and weight are less common in this role and made the comparison harder.";
    return "Their height and weight are familiar enough for this role to support a reasonable comparison.";
  }

  function reasonsFor(score, body) {
    const contributions = Array.isArray(score?.top_contributions) ? score.top_contributions.slice(0, 2) : [];
    const reasons = contributions.map(contributionSentence);
    if (!reasons.length) {
      reasons.push(noScoreReasons[score?.status] || "The model did not have enough familiar evidence to show a responsible number.");
    }
    if (reasons.length < 2) reasons.push(bodyReason(body));
    return reasons.slice(0, 2);
  }

  function deepLink(config) {
    const url = new URL("../friendly/", document.baseURI);
    url.searchParams.set("player", config.playerId);
    url.searchParams.set("sport", config.target.sport);
    url.searchParams.set("role", config.target.role);
    url.searchParams.set("basis", config.basis);
    return url.href;
  }

  function renderStory(manifest, config, player, detail, index) {
    const payload = detail.targets?.[config.target.sport]?.roles?.[config.target.role];
    if (!payload) throw new Error(`Story target is unavailable for ${config.playerId}`);
    const transfer = payload.transfer_guesstimate;
    const body = payload.body_fit;
    const native = detail.native?.observed;
    const transferAvailable = transfer?.status === "available" && finite(transfer.value);
    const bodyAvailable = body?.status === "available" && finite(body.value);
    const nativeAvailable = finite(native?.value);

    const card = element("article", "story-card");
    card.id = `story-${index + 1}`;
    const intro = element("div", "story-intro");
    append(
      intro,
      append(
        element("div", "story-number"),
        element("span", "", config.editorial.category),
        element("span", "", String(index + 1).padStart(2, "0")),
      ),
      element("h3", "", player.name),
    );
    const route = element("p", "route");
    append(
      route,
      element("strong", "", `${sportLabel(manifest, player.sport)} ${roleLabel(manifest, player.sport, player.role)}`),
      element("span", "", " → "),
      element("strong", "", `${sportLabel(manifest, config.target.sport)} ${payload.label || roleLabel(manifest, config.target.sport, config.target.role)}`),
    );
    append(intro, route, element("p", "story-hook", config.editorial.hook));
    const link = element("a", "story-link", "Explore this comparison");
    link.href = deepLink(config);
    link.append(element("span", "", "→"));
    intro.append(link);

    const bodySection = element("div", "story-body");
    const scores = element("div", "score-row");
    if (transferAvailable) {
      const note = transfer.value >= 99.5
        ? "The result reached the model’s upper limit. That does not mean perfect ability."
        : `${comparisonBand(transfer.value)} among this role’s comparison group.`;
      scores.append(scoreBox("Cross-sport comparison", transfer.value, note));
    } else {
      scores.append(scoreBox(
        "Cross-sport comparison",
        null,
        `${noScoreReasons[transfer?.status] || "The result was not reliable enough to show."} No score is not zero.`,
        { noScore: true },
      ));
    }
    scores.append(bodyAvailable
      ? scoreBox(
        "Build similarity",
        body.value,
        `${bodyBand(body.value)} for this role. This describes height and weight, not ability.`,
      )
      : scoreBox("Build similarity", null, "The saved measurements are not enough for this comparison.", { noScore: true }));
    scores.append(nativeAvailable
      ? scoreBox(
        "Own-role rank",
        native.value,
        `Higher than about ${format(native.value)}% of players in the athlete’s real role.`,
      )
      : scoreBox("Own-role rank", null, "No reliable own-role score is available for this season.", { noScore: true }));
    bodySection.append(scores);

    const explanation = element("div", "story-explanation");
    const reasonBlock = element("div");
    reasonBlock.append(element("h4", "", transferAvailable ? "What moved the comparison" : "Why no number appears"));
    const reasonList = element("ul", "reason-list");
    reasonsFor(transfer, body).forEach((reason) => reasonList.append(element("li", "", reason)));
    reasonBlock.append(reasonList);
    const lesson = element("div", "lesson");
    append(lesson, element("h4", "", "Why this case matters"), element("p", "", config.editorial.lesson));
    append(explanation, reasonBlock, lesson);
    bodySection.append(explanation);

    const caution = element("p", "story-caution");
    const cautionLead = element("strong", "", "Keep in mind: ");
    caution.append(cautionLead);
    caution.append(transferAvailable
      ? "This is an exploratory role comparison, not the chance that the athlete could successfully change sports."
      : "The model’s refusal is intentional. Showing no score is more honest than treating an unfamiliar athlete as average.");
    bodySection.append(caution);
    append(card, intro, bodySection);
    return card;
  }

  async function initialise() {
    try {
      const manifest = await fetchJson("manifest.json");
      const players = new Map((manifest.players || []).map((player) => [player.id, player]));
      const stories = await Promise.all(storyConfig.map(async (config) => {
        const player = players.get(config.playerId);
        if (!player) throw new Error(`Story player is unavailable: ${config.playerId}`);
        return { config, player, detail: await fetchJson(player.detail_path) };
      }));
      const fragment = document.createDocumentFragment();
      stories.forEach(({ config, player, detail }, index) => {
        fragment.append(renderStory(manifest, config, player, detail, index));
      });
      storyList.replaceChildren(fragment);
      storyList.setAttribute("aria-busy", "false");
      const seasons = manifest.snapshot?.latest_seasons || [];
      document.querySelector("#snapshot-note").textContent = `Live examples from ${manifest.counts?.players?.toLocaleString("en-US") || "the saved"} player profiles · seasons ${seasons.join(", ") || "unavailable"}`;
      document.querySelector("#announcement").textContent = "Six guided player stories are ready.";
    } catch (_) {
      const error = document.querySelector("#app-error");
      error.hidden = false;
      error.textContent = "The guided examples could not be loaded from the shared project export. Build the all-role portal data, then try again.";
      storyList.replaceChildren(element("p", "empty-state", "The player stories are unavailable."));
      storyList.setAttribute("aria-busy", "false");
      document.querySelector("#announcement").textContent = "The guided player stories could not be loaded.";
    }
  }

  initialise();
})();
