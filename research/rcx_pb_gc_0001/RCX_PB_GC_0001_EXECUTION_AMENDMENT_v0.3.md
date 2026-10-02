# RCX-PB-GC-0001 — Execution Amendment v0.3

**Date frozen:** 2026-10-01  
**Scope:** execution semantics only; the v0.1 scientific question, admissible model families, required null families, primary scores, and pass gates remain controlling.  
**Status:** PRE-SCORING LOCK. No sealed-test draw truth has been used to choose a model, threshold, repair, or hyperparameter under this amendment.

## 1. Why this amendment exists
The v0.1 preregistration froze the scientific architecture before the complete current-matrix physical corpus was assembled. During implementation, several execution details were still underspecified: the numeric family-wise threshold, exact matched-null correction, deterministic null seeds, sealed-truth separation, and handling of purely typographic date tokens in the official source. This amendment closes only those execution ambiguities before scientific scoring.

No failed explanation from v0.1 is revived. Printed ball labels remain categorical object identifiers inside their physical sets; label arithmetic is not introduced.

## 2. Authoritative corpus and immutable interval
- Source: `https://cdn.powerball.com/v01/media/powerball-pre-test.pdf`
- Matrix: `5/69 + 1/26`
- Start: `2015-10-07`
- Cutoff: `2026-09-28`
- Execution-A rows: `Pre-test` and official `Draw`; `Post-test` excluded.
- Source bytes and extracted text are hashed with SHA-256.
- Raw source tokens/lines are retained in the source vault. Normalized fields never overwrite raw fields.

## 3. Syntax-only date normalization
Exactly one automatic source repair class is allowed: `MM/DDYY -> MM/DD/YY`.

It is permitted only when: (1) the token matches `^[0-9]{2}/[0-9]{4}$`; (2) insertion of the missing slash yields one valid calendar date; (3) no ball, machine, set, type, order, or outcome field changes; (4) raw and corrected tokens are retained; and (5) a `SYNTAX_ONLY_DATE_NORMALIZATION` anomaly is written.

No other malformed or ambiguous source metadata is automatically repaired. Any other unparsed event line, impossible date, missing/extra expected draw date, wrong pretest/draw count, range error, duplicate white label in one row, or split inconsistency is blocking. Hardware/set changes inside a date are preserved and logged as nonblocking `SOURCE_REGIME_DISCONTINUITY`.

## 4. Sealed-truth isolation
The v0.1 split remains unchanged: `SHA256("RCX-PB-GC-0001|" + YYYY-MM-DD)`, first byte modulo 10; 0–5 development, 6–7 validation, 8–9 sealed test.

Before discovery/model selection, sealed official draw content is masked from working artifacts. Same-date sealed pretests/context remain available. The full source/sealed-truth vault is not opened for scoring until a final search manifest is frozen and SHA-256 committed.

## 5. Search-family correction and null count
Family-wise significance is frozen at **FWER alpha = 0.01**.

For each required null family, rerun the complete model-search/selection pipeline including every candidate/hyperparameter searched on real data. Each null replicate statistic is the maximum selection statistic attained anywhere in that replicate's searched family.

Use **9,999 deterministic replicates per null family**. For null family `f`:
`p_f = (1 + #{b : T_null[f,b] >= T_observed}) / 10000`.

Across the six required v0.1 null families, apply Holm-Bonferroni at family-wise alpha 0.01. All six adjusted tests must pass for gate 2.

Null seed: `SHA256("RCX-PB-GC-0001|NULL|" + null_family + "|" + zero_padded_replicate)`, using the first 8 digest bytes as an unsigned integer.

## 6. Operational definitions of frozen nulls
1. **Fair physical-record null** — replace each five-white extraction by a uniform sample without replacement from 1..69 and each Powerball by uniform 1..26; preserve dates, row types/order, machine IDs, ball-set IDs, hardware schedule.
2. **Chronology shuffle** — shuffle complete date blocks within identical draw `(wm,ws,pm,ps)` strata where estimable; strata with fewer than four dates fall back to `(ws,ps)`, with fallback recorded.
3. **Object relabeling within sets** — independently draw one random bijection of labels for each white set ID and PB set ID and apply it consistently to all occurrences of that set.
4. **Pretest-order destruction** — within each date, uniformly permute the four complete pretest rows; extraction positions inside rows stay unchanged; draw row untouched.
5. **Pretest-to-draw reassignment** — reassign complete four-pretest blocks among dates within identical draw `(wm,ws,pm,ps)` context, with the same `(ws,ps)` sparse-stratum fallback; draw blocks remain on original dates.
6. **Outcome-only marginal null** — permute complete official draw outcomes among dates within the same matrix, preserving five-without-replacement structure and empirical draw-outcome marginals; pretests/hardware fixed.

## 7. Selection objective
Validation compares candidates by:
`S = mean held-out log-score improvement over fair without-replacement baseline - MDL_penalty`,
with `MDL_penalty = 0.5 * k * ln(N) / N`, `k` the fitted scalar degrees of freedom and `N` scored target draws. Undefined/non-finite candidates are ineligible.

Development fits/tunes the frozen grid; validation chooses the final explicit grammar/hyperparameter setting. Sealed truth cannot break ties. Exact ties: lower `k`, then lower memory order, then lexical model ID.

## 8. Reconstruction vs forward-only
Global reconstruction may use both temporal sides. Forward-only may use no observation later than the target date; same-day pretests are available. Scores are never conflated.

Single-event sealed holes are primary. Growing contiguous holes of 2,4,8,16 dates are secondary. Starts are outcome-blind using `SHA256("RCX-PB-GC-0001|HOLE|" + length + "|" + start_date)` and non-overlap selection. A block is primary only if every target draw belongs to the sealed-test assignment.

## 9. Stability gate
Operationalize the >=80% grammar-class stability gate with 200 deterministic moving-block bootstrap resamples of development+validation dates, block length 16 dates. Require the same final grammar/constraint class in >=0.80 of resamples when >=180/200 are identifiable; otherwise UNIDENTIFIABLE.

## 10. Hardware/ball-set transfer gate
A regime-transition target is a date where at least one draw-context identifier `(wm,ws,pm,ps)` first appears after at least 30 earlier matrix dates. If at least 10 subsequent target dates contain that new identifier, fit the selected grammar class on only pre-transition dates, freeze parameters, and score the first 10 eligible dates without refit. If no transition meets support, gate 4 is UNIDENTIFIABLE rather than assumed PASS.

## 11. Claim boundary
This amendment cannot itself produce an EUREKA. PASS still requires every v0.1 gate. High-confidence Reality-Code status still requires independent held-out-era or live prospective replication.
