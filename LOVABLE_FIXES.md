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
