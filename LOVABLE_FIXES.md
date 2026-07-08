# Lovable Fix Spec — stats-cruncher-mlb ("Diamond Edge")

Paste the prompts below into the Lovable chat one at a time (they're ordered by impact).
Each is self-contained. Fix 1 and Fix 2 are the ones that directly caused the July 2
losses — do those before anything else.

---

## Fix 1 (P0) — Best Play must respect the veto layer

> In the Daily Slate screen, the "BEST PLAY" header banner is selected by raw confidence
> score and ignores the robustness-veto / PASS status on the pick cards. On 2026-07-02
> every card was PASS with stake 0u, yet the banner promoted "MIL ML @ 1.46 conf 99/100".
> Change the Best Play selection to: (1) only consider picks whose final status is
> BET-eligible (not PASS, not vetoed, stake > 0); (2) if no pick qualifies, render a
> prominent "NO BETS TODAY — no price on the board beats sharp fair" state instead of a
> best play; (3) the game-tile grid must show the same status as the card detail — a
> vetoed pick must never display its boosted edge as if actionable. Add a regression test:
> a slate where all picks are vetoed must produce no Best Play.

## Fix 2 (P0) — Rebuild edge math around sharp fair, not model-vs-book

> Replace the edge calculation. Current behavior computes edge from the internal model
> probability (after a hit-rate "calibration boost") against the book price, producing
> raw edges of +16 to +36pp, which are impossible. New pipeline:
> 1. Compute Pinnacle no-vig fair probability p_fair for each market (multiplicative
>    de-vig on the two-way prices from the Pinnacle screenshot/API anchor).
> 2. Shrink the model toward market: p_final = w × p_model + (1 − w) × p_fair, with
>    w = 0.30 × data_quality_score (data_quality_score ∈ [0,1]; CRITICAL-missing fields
>    push it toward 0). w must never exceed 0.30.
> 3. Edge = p_final × book_decimal_odds − 1. Bet threshold: edge ≥ +2.0%. Everything
>    below that is PASS regardless of confidence.
> 4. Hard rule: if |p_model − p_fair| > 4pp, cap p_final at p_fair ± 4pp and add a
>    "model disagrees with sharps" warning that REDUCES the confidence score.
> 5. If book total line ≠ Pinnacle total line (e.g. 7.0 vs 7.5), do not compare prices
>    directly — either adjust for push probability at the intervening key number or veto
>    with the existing line-mismatch rule. Never surface EV computed across different lines.

## Fix 3 (P0) — Delete the hit-rate "calibration boost"

> Remove the calibration step that adjusts probabilities using team hit rates (e.g.
> "model 77% → 80% (MIL hit rate 64%)"). It moves probabilities AWAY from market
> consensus based on tiny samples and inflated both losing picks on 2026-07-02. Replace
> with the market-shrinkage from Fix 2. Keep a calibration PAGE that tracks Brier score
> and reliability curves of p_final vs outcomes over time, but calibration must only ever
> shrink toward 50%/market, never boost conviction.

## Fix 4 (P1) — Sim inputs: xERA/xwOBA, not ERA

> The simulator currently weights starter ERA. The Savant panel already fetches xERA and
> xwOBA — use them: starter run expectation = park-adjusted blend of xERA (weight ~0.7)
> and ERA (~0.3), with the blend shifting further toward xERA when innings pitched is low
> (< 60 IP: 0.85/0.15). The ΔxERA regression flags (e.g. Misiorowski +1.94, Bryce Miller
> 1.97 ERA vs 7.12 xERA) must change the projection, not just render as a chip.

## Fix 5 (P1) — Park model, especially Coors

> Add a park-factor layer: (1) multiply projected runs by park run factor (Coors ~1.28,
> use a static table for all 30 parks as v1); (2) scale the run-distribution variance by
> park (Coors sigma multiplier ~1.15-1.20); (3) recompute win probability from the
> widened distribution — higher variance must compress ML probabilities toward 50%. A
> road team the sim makes 68% at a neutral park should land ~55-58% at Coors. Validate:
> re-run 2026-07-02 MIA@COL; the output must be ≤ 58% MIA.

## Fix 6 (P1) — Injuries must hit the sim inputs

> The news layer detected "Miami's bullpen significantly depleted, four relievers on IL
> (Bender, Junk, Ekness, Nardi)" but the sim still used the season-long bullpen ERA/effPen.
> When the news/injury feed identifies IL players: (1) for relievers, recompute effPen
> from the ACTIVE roster only, or apply +0.35 runs/9 per high-leverage arm lost as a
> fallback; (2) for position players, apply a lineup-runs penalty; (3) show the adjusted
> vs unadjusted number on the card so the effect is auditable.

## Fix 7 (P1) — Stop simming on placeholder data

> Bullpen ERAs on 2026-07-02 repeated fallback constants (away 4.20 / home 3.10 in six of
> nine games) while every card showed "DATA QUALITY: INCOMPLETE — CRITICAL missing".
> Rules: (1) fallback/default values must set data_quality_score for that input to 0 (which
> via Fix 2 collapses model weight toward market); (2) any game with ≥2 CRITICAL-missing
> inputs is auto-PASS; (3) render placeholder-derived numbers in a distinct "estimated"
> style so they can't be mistaken for real data; (4) the effects engine reporting
> umpire/weather/starter-variance/defensive-K as `disabled` must subtract from confidence.

## Fix 8 (P2) — Confidence score that means something

> Confidence 99/100 on a vetoed, -6.7% EV bet destroys trust in every other number.
> Redefine confidence = monotone function of (a) EV vs sharp fair at the actual book
> price, (b) data completeness, (c) model-market agreement (closer = higher), (d) line
> freshness. A pick the market disagrees with by >10pp must not exceed ~40. Vetoed picks
> display no confidence number at all — just the veto reason.

## Fix 9 (P2) — Grade on CLV and Brier, not just W/L

> In Post-Mortem: for every surfaced pick record the Pinnacle closing line and report
> (1) CLV in pp and (2) rolling Brier score of p_final vs outcomes, alongside W/L and
> ROI. Add a banner rule: if 30-day CLV is negative, show "model is not beating the
> close — reduce stakes" on the Daily Slate.

## Fix 10 (P2) — Staking honesty

> With Fix 2's +2% EV threshold, most days will produce 0-2 bets. Kelly stake =
> 0.25 × kelly_fraction(p_final, odds), capped at 1.5u. The unit-size widget should show
> expected bets/week (~3-5) so zero-bet days read as the system working, not broken.

---

### Acceptance test for the whole batch

Re-run the archived 2026-07-02 slate after Fixes 1-7:
- MIL ML: p_final ≤ 64.5%, EV at 1.46 ≈ -6%, status PASS, no Best Play promotion.
- MIA ML: p_final ≤ 58%, EV at 1.72 negative, PASS.
- Slate output: "NO BETS TODAY", average |raw edge| < 5pp, zero picks with conf > 60.

---

## Fix 11 (P0) — Timeout cascade, RotoWire lineups, partial Pinnacle coverage

> Three related fixes for the Daily Slate screen: the 504/timeout cascade, the
> lineup source, and partial Pinnacle anchor coverage.
>
> CONTEXT (from production console logs): Page load fires ~26 parallel calls to
> the mlb-stats edge function (action=lineup&teamId=X&date=...), which each hit
> MLB's API upstream. They 504, SlateContext times out ("slate context timed
> out — rendering without context"), and the app renders from a fallback that
> discards data that DID load: console showed "fast pinnacle anchor coverage:
> 9 games" while Slate Health rendered "0 Pinnacle · 0 of 13 games". Four games
> failed analyse with HTTP 504 and fell back to client-side recompute. Pinnacle
> posting lines late is NORMAL (bet365 posts full slates earlier) — partial
> Pinnacle coverage must be handled per-game, never slate-wide.
>
> FIX A — RotoWire is the lineup source (this is what the Context URL field is
> for): (1) New edge function action rotowire-lineups&date=YYYY-MM-DD fetching
> https://www.rotowire.com/baseball/daily-lineups.php (today) or
> ...daily-lineups.php?date=tomorrow server-side — ONE request replaces all 26
> per-team MLB API calls; realistic User-Agent. (2) Parse every game box:
> teams, game time, starting pitchers (name + handedness), 9 batting slots per
> team (name, position, handedness), and the per-team "Confirmed Lineup" vs
> "Expected/Projected Lineup" badge. (3) Cache in table rotowire_lineups
> (key: date, TTL 10 min); serve stale on upstream failure; 8s upstream
> timeout; on failure return HTTP 200 {status:"unavailable", cached:...} —
> never 504. (4) Client makes exactly ONE lineups call per slate load; delete
> the per-team fan-out; keep MLB statsapi only as fallback behind the same
> cache. (5) Confirmed lineup = full weight; projected = uncertainty haircut +
> "projected lineup" chip; respect the date param of a pasted RotoWire URL.
>
> FIX B — SlateContext progressive, not all-or-nothing: (1) Context value
> { odds, anchors, lineups, bakedBlocks, status per resource }; each resource
> commits the moment it resolves. (2) Delete the "rendering without context"
> fallback; fast-anchor results write into the same store Slate Health reads.
> (3) Max 4 concurrent edge calls, retry 5xx twice with backoff+jitter;
> lineups/blocks never block first render. (4) Auto-retry failed bakes in the
> background and re-render that card when the block arrives.
>
> FIX C — Partial Pinnacle coverage is normal: (1) Per-game anchor hierarchy:
> pinnacle → consensus (de-vigged bet365, shrunk 1pp toward 50%) → none.
> (2) Slate Health reports true coverage ("9 of 13 Pinnacle · 4 consensus"),
> never 0-of-N when per-game anchors exist; remove the slate-wide "NO SHARP
> ANCHOR" state for partial coverage. (3) Tiers per game: pinnacle = LOCK-
> eligible, consensus = cap GOOD, none = auto-PASS; one uncovered game never
> caps the rest. (4) Refresh Data + auto-refresh every 15 min re-runs ONLY the
> anchor fetch and re-prices edges/tiers from existing sim results, logging
> upgrades ("CIN@MIL anchor upgraded consensus → pinnacle").
>
> ACCEPTANCE: 13-game slate with MLB API delayed 30s → zero 504s, first render
> < 3s, per-game anchors shown, Slate Health "9 of 13 Pinnacle · 4 consensus",
> no "rendering without context" log. rotowire-lineups returns all games for
> date=tomorrow with per-team confirmed/projected from one upstream fetch;
> second call within 10 min served from cache. Killing the edge function
> mid-load still renders cached lineups with a stale banner.

---

## Implementation log

### Shipped 2026-07-07 (Lovable pass 3)
- **Workstream A — pricing reframe**: `pricePctVsFair` per pick (replaces the
  constant "+4.0pp" bug), GOOD/FAIR/POOR/UNPRICED badges (≥ −1.5% / to −3.5% /
  below), POOR warns + halves ¼-Kelly stake but never vetoes, `ev > 0` filter
  removed so confident plays surface at any price with an honest badge.
  Files: consensus.ts, pickAxes.ts, MatchupTile.tsx, TonightsConfidentPlays.tsx,
  matchupSynthesis.ts.
- **B4 — luck classifier**: gap = xwOBA − wOBA, ±0.008 dead-zone, direction
  fixed (positive gap = COLD_UNLUCKY/up), symmetric unit tests. Note: the KC
  07-06 example (.324 vs .328) is |Δ|=.004 → NEUTRAL by rule; correct outcome.
- **B5 — compounding risk**: High starter dependency + red SP flag (xERA gap
  > 1.0, or location-split / recent-form once B1/B2 populate) → conf −15
  stacked past the ±10 stability cap, reason in breakdown tooltip.

### Pending (green-lit as next focused build)
- **Golden-slate regression harness** (2026-07-02 + 2026-07-06 fixtures,
  per-game before/after diff table, convergence assertion vs Pinnacle fair).
- **B1** location-conditioned starter projection (Sánchez 0.86H/3.89R case).
- **B2** symmetric recent-form term (±0.8 RA9 cap, 15% weight).
- **B3** handedness-split offense (PHI .669 OPS vs LHP case).
- Acceptance still open: 07-06 PHI@KC → PHI ~58-62%, conf ≤ 55 (gated on B1/B2).

---

## Fix 12 (P1) — Sharp context features (signal vs narrative)

> GOVERNING PRINCIPLE: every dramatic baseball event has two readings — a
> DURABLE STATE CHANGE (signal, predicts the next game) and a NARRATIVE
> (fade, already happened / emotional / small-sample). The model ingests the
> first and must NEVER add a boost for the second. A pulled perfect game =
> bullpen now exposed (signal), not "team choked" (fade). A blown 99% lead =
> pen is broken this week (signal), not "demoralized team" (fade).
>
> SIGNAL FEATURES TO ADD (ranked; each ships behind the golden-slate harness
> and must shrink slate-avg |model − Pinnacle fair| or it is reverted):
> 1. Rolling bullpen form (last 14d): pen ERA/HR-rate + blown-save% as a term
>    separate from season effPen. Drives close-game ML down and late team
>    totals under. Books lean on season pen numbers — this is the edge.
> 2. High-leverage arm availability: from the freshness dots (HEAVY 3D). Top
>    1-2 relievers gassed → widen that team's late-game run distribution.
> 3. RA9 instead of ERA for run prevention + team defense (OAA/DRS). Unearned
>    runs are real (Yankees: 15 of 43 runs unearned during the skid). Bad
>    gloves add runs ERA/xERA can't see.
> 4. Starter-exit → bullpen-exposure compounding: when the projection leans
>    on the SP going deep AND the pen is weak, treat as ONE compounding risk
>    (wider downside), not two independent ones.
> 5. Starter injury/workload/fatigue flags: recent IL stint, heavy workload
>    vs baseline, or "start pushed back / extra rest" news → downgrade the
>    starter projection even if the season line is elite (Ohtani case).
> 6. Recency-weighted, REGRESSED team form (last 30d, ~25% weight, regressed
>    toward season) AND opponent-adjusted (a bad stretch vs elite opponents
>    means less — Padres' collapse came vs Dodgers/Cubs).
> 7. Catcher-pitcher pairing: starter ERA/xERA split by tonight's catcher
>    (min sample); flag backup/personal-catcher starts (Ohtani 0.74 w/ Smith
>    vs 4.34 w/ Rushing). Cheapest unique edge — absent from public models.
> 8. Hot/cold hitter form + availability: key bat in/out of lineup and its
>    regressed recent form. Cap hard — an 11-HR-in-11-games heater will not
>    continue at that rate.
>
> FADE RULES (the model must NEVER add a positive adjustment for these):
> revenge spots (ex-team, booing crowd); momentum from a dramatic
> comeback/collapse; manager firing or ejection "spark"; new-manager
> first-game bump; a single blowout's run margin; clubhouse drama. The public
> overbets all of these, so if anything the value is the other way — but do
> not code a contrarian boost either; just refuse to move the number.
>
> BUILD ORDER: harness first, then features 1→8, one commit each with the
> before/after per-game diff table. Weather (wind at total-friendly parks)
> and AL/NL league-strength adjustment are v2, lower priority.
