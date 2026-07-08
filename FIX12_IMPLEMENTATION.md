# Fix 12 — Implementation Guide (Sharp Context Features)

Paste each prompt into the Lovable chat in order. Ship one per commit, run the
golden-slate harness between each. Governing rule (from Fix 12): ingest DURABLE
STATE (signal), never add a boost for NARRATIVE (revenge, momentum, manager
sparks). Every split is regressed for sample size before it touches the sim.

Data sources (Supabase edge functions can reach these):
- MLB StatsAPI  https://statsapi.mlb.com/api/v1/  (free, no key): splits
  (homeAndAway, byMonth, statSplits sitCodes vl/vr), game logs (gameLog),
  rosters/IL (/teams/{id}/roster), blown saves (team pitching stats),
  schedule/results.
- Baseball Savant CSV leaderboards: expected_statistics (xERA/xwOBA),
  outs_above_average (team+player OAA/defense), statcast-park-factors.
Verify response shapes at build time; these APIs drift.

Foundation (Prompt A) and Pitchers (Prompt B) are delivered in chat. Below are
Prompts C–F.

---

## PROMPT C — Bullpen intelligence

Implement team bullpen features in 'stats-intel', regressed + cached, gated on
the harness. This is the highest-edge feature set (books lean on season pen
numbers; a pen broken THIS WEEK is knowable and mispriced).

Per team:
1. ROLLING 14-DAY BULLPEN FORM: from relief-pitching game logs (split SP vs RP
   by appearance), compute last-14-day bullpen RA9 and HR/9, regressed toward
   season pen (k≈80 BF). Enter as a term SEPARATE from season effPen. Drives
   close-game ML down and late team totals under for a team with a hot pen ERA.
   (Validates on the Nats-collapse pattern: a pen at 11+ RA9 over two weeks must
   materially lower that team's win prob in one-run-game states.)
2. BLOWN-SAVE RATE (14d and season): from team pitching stats + game logs.
   High recent blown-save rate widens the late-game variance for leads held.
3. HIGH-LEVERAGE ARM AVAILABILITY: from each reliever's pitch counts over the
   last 3 days (game logs by date). If a team's top 1-2 leverage arms are gassed
   (back-to-back-to-back or >40 pitches in 2 days), widen that team's 7th-9th
   inning run distribution. Surface on the freshness dots already on the card.
4. STARTER-EXIT → BULLPEN EXPOSURE (compounding): when the win projection leans
   on the SP going ≥6 IP AND the rolling pen form is bottom-tier, treat as ONE
   compounding risk (wider downside tail + confidence reduction), not two
   independent terms. (Yuri Perez pulled from a perfect game → pen implodes.)

ACCEPTANCE via harness: a fixture team with a bottom-5 rolling pen loses win
prob in close-game states vs its season-pen baseline; global gap-vs-Pinnacle
assertion holds; diff table printed.

---

## PROMPT D — Team & player (offense + defense)

Per team, cached + regressed, gated on harness:
1. HANDEDNESS-SPLIT OFFENSE: StatsAPI team statSplits sitCodes vl/vr
   (group=hitting). Project each lineup's runs from its wOBA/OPS vs tonight's
   starter hand, regressed toward overall team offense (k≈200 PA; regress 50%
   toward 1.0 when PA vs that hand < 400). (Validates on 07-06: PHI .669 OPS
   vs LHP → projected as a bottom-5 offense that night, not their top-5 self.)
2. RECENCY-WEIGHTED + OPPONENT-ADJUSTED FORM: last-30-day team wOBA and RA9
   from schedule/game logs at ~25% weight, regressed toward season, THEN
   adjusted for strength of schedule (a bad stretch vs elite opponents means
   less — Padres' collapse came vs Dodgers/Cubs). Never chase a raw hot/cold
   streak.
3. TEAM DEFENSE via RA9 + OAA: use RA9 (earned+unearned) for run prevention,
   not just ERA (Yankees allowed 1/3 of skid runs unearned). Add team OAA from
   Baseball Savant as a small run-prevention modifier. Bad gloves add runs the
   pitching stats can't see.
4. HOT/COLD HITTER + AVAILABILITY: key bat's regressed last-15 form and whether
   they're in tonight's lineup (from RotoWire). Cap hard — an 11-HR-in-11-games
   heater does not continue at that rate; this refines lineup strength, it does
   not create a mispriced edge on its own.

ACCEPTANCE via harness: PHI@KC 07-06 game total projection drops (PHI a weak
LHP-facing offense); a fixture team with negative OAA loses run-prevention;
global assertion holds; diff table printed.

---

## PROMPT E — Ballpark model

1. PARK RUN FACTOR: static table of all 30 parks v1 (Coors ~1.28, GABP,
   Fenway, etc.); multiply projected runs by the venue factor. Later: compute
   from Baseball Savant statcast-park-factors and cache.
2. PARK VARIANCE: scale the run-distribution sigma by park (Coors ~1.15-1.20).
   Higher variance must compress ML win probabilities toward 50%.
3. Recompute win prob from the widened distribution, not just the mean.

ACCEPTANCE via harness: re-run 2026-07-02 MIA@COL → MIA win prob ≤ 58% (was
68%); a neutral-park game is unchanged; diff table printed.

---

## PROMPT F — Fade guardrails + confidence wiring + full acceptance

1. FADE GUARDRAILS (hard rules, with unit tests): the model must NEVER add a
   positive adjustment for revenge spots, momentum from a comeback/collapse,
   manager firing/ejection "spark", new-manager first-game bump, a single
   blowout's run margin, or clubhouse drama. If the news/narrative layer emits
   any of these tags, they may only inform text on the card — they must not
   move the projection or confidence. Add tests asserting a revenge/momentum
   tag produces zero projection delta.
2. CONFIDENCE WIRING: fold the new signal features into the confidence score
   per the two-axis model (confidence = market-anchored win prob + agreement +
   stability; price quality separate). New stability inputs: bullpen-form
   stability, defense, park extremity (Coors caps confidence), starter fatigue
   flags. Compound-risk stacks (already in B5) now also fire on the new
   locationSplit / recentForm / xeraGap / bullpen-exposure flags.
3. CALIBRATION: the Confidence Calibration panel must show these features
   improved calibration — buckets should move toward their nominal hit rate
   over the graded sample. If a bucket is off >5pp over 30+ picks, auto-shrink
   the stability bonuses.

FULL ACCEPTANCE (run the whole harness):
- 07-06 PHI@KC: PHI ~58-62%, conf ≤ 55, price badge POOR at bet365 1.45,
  KC +1.5 surfaced as the price-side lean.
- 07-02 MIL@STL: Misiorowski projection regresses up, MIL < 65%.
- 07-02 MIA@COL: MIA ≤ 58% (park model).
- Slate-average |model − Pinnacle fair| is LOWER than the pre-Fix-12 baseline
  on both fixtures.
- No fade tag ever moved a projection (tests green).
- Print the final before/after diff table for both fixtures in the PR.
