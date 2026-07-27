#!/usr/bin/env bash
# Create the Colony umbrella + A/B/C sub-issues on GitHub.
# Requires: gh auth with Issues write permission on ave19/colony
set -euo pipefail

REPO="${REPO:-ave19/colony}"
cd "$(dirname "$0")/.."

if ! gh api "repos/${REPO}" --jq .full_name >/dev/null 2>&1; then
  echo "Cannot access repo ${REPO}. Check gh auth." >&2
  exit 1
fi

# Probe issue create permission
if ! gh api "repos/${REPO}/issues" --method POST \
  -f title="[permission probe — delete me]" \
  -f body="probe" >/tmp/colony-issue-probe.json 2>/tmp/colony-issue-probe.err; then
  echo "ERROR: Cannot create issues on ${REPO}." >&2
  echo "Your GitHub token needs Issues: Read and write on this repository." >&2
  echo "Fine-grained PAT: grant Issues (Read and write), then: gh auth login" >&2
  cat /tmp/colony-issue-probe.err >&2 || true
  exit 1
fi
PROBE_N=$(jq -r .number /tmp/colony-issue-probe.json)
gh api "repos/${REPO}/issues/${PROBE_N}" --method PATCH -f state=closed -f state_reason=not_planned >/dev/null
echo "Issue permission OK (closed probe #${PROBE_N})"

create_issue() {
  local title="$1"
  local body="$2"
  gh issue create -R "$REPO" --title "$title" --body "$body"
}

echo "Creating umbrella..."
UMBRELLA_URL=$(create_issue "UMBRELLA: Colony — playable ladder (A → B → C)" "$(cat <<'EOF'
## Goal

Build **Colony** as a science-driven orbital logistics sim: player-authored goals → needs → contracts, real orbital mechanics, formation-based systems, constrained exponential growth. Deliver in three milestones (**A → B → C**).

See also: `docs/PLAYABLE_LADDER.md` in the repo.

## Architecture decisions

| Area | Decision |
|------|----------|
| Orbit | Planned transfers (not hand-pilot); real mechanics; fuel vs time options; Δv to orbit/escape |
| Propellant | Typed cargo + Δv UI; multiple drives; materials may block some drive types |
| Time | Default 1× while process runs; event calendar; alarms; vote-warp to next event; wall-clock catch-up on wake |
| Hosting | Self-host colony room (Python); VPS optional; desk PC offline = room offline |
| Tech | Full know-how on arrival; 2536-plausible science; substitutes with mass/efficiency penalties; no research XP tree |
| Systems | Same tech every run; formation-based gen; stable orbits; difficulty metric; filter traps; pick star then commit |
| Materials | Atoms → processes → compounds; location choices (ISRU vs central); co-reactants matter (CH₄ needs O₂) |
| Growth | Constrained exponential; throughput-limited (e.g. 10 t Fe/mo still progresses) |
| View | v1 system map only (isometric/god's-eye web); no NMS zoom yet; no mid-game galaxy UI |
| Start | Heavy but limited loadout; customize before transit; scan sats, mining bots, tiny ship fabs |
| Plans | Player goals → needs → contracts (not NPC quests); multiple projects can conflict |
| MP (B) | Shared colony; corps + claims; credits + barter; demand from structure; invite-based |
| AI (C) | Suggest goals (cascades to contracts); optional full auto “watch AI solve” |
| Score (later) | Colony-ship production rate |
| Stack | Python server + web client |

## Milestones

- **A** — Solo vertical slice (first playable)
- **B** — Multiplayer corps
- **C** — Director AI

## Out of scope (A/B/C ladder)

- Public matchmaking / managed hosting
- Site-level Factorio / NMS zoom
- Full surface transport tree as required depth
- Deep fusion as mandatory path
- True n-body chaos
- Post-system campaign UI beyond pre-game star pick
- Rich multi-corp market polish

## Acceptance criteria

### A
- [ ] Star pick → arrive in generated stable system
- [ ] Map + base plan spawns needs/contracts
- [ ] Bootstrap + one real transfer-option haul
- [ ] 1× + wall-clock catch-up
- [ ] Fully solo playable

### B
- [ ] 2+ players in one room on one system
- [ ] Corps claim assets; contracts fillable cross-corp
- [ ] Co-op loop: base needs ↔ harvester ↔ haul route
- [ ] Self-host/VPS model still holds

### C
- [ ] Director proposes sensible goals from known state
- [ ] Accepting a suggestion spawns real contracts
- [ ] Auto mode can progress without cheating physics
- [ ] Human can override / disable

## Notes

- Sync code to `origin` regularly during implementation.
- Sub-issues are linked below as they are created.
EOF
)")
UMBRELLA_N="${UMBRELLA_URL##*/}"
echo "Umbrella: $UMBRELLA_URL"

sub() {
  local id="$1"
  local title="$2"
  local depends="$3"
  local what="$4"
  local criteria="$5"
  create_issue "[${id}] ${title}" "$(cat <<EOF
Sub-issue of: #${UMBRELLA_N}
Milestone ID: ${id}
Depends on: ${depends}

## What
${what}

## Acceptance criteria
${criteria}
EOF
)"
}

echo "Creating Milestone A issues..."
A1=$(sub A1 "Sim core: time, events, catch-up, vote-warp stub" "—" \
  "Implement the shared simulation clock: default 1× while the process runs; event calendar; player alarms; stub for vote-to-warp-to-next-event; wall-clock catch-up when the process wakes." \
  "- [ ] Sim advances at 1× when running
- [ ] Events can be scheduled and listed
- [ ] Alarms can be set on events
- [ ] Catch-up advances sim from last time to wall clock on wake
- [ ] Vote-warp stub exists (even if single-player auto-approves)")
A1N=${A1##*/}; echo "  A1 #$A1N"

A2=$(sub A2 "System generator: formation priors, stable orbits, difficulty, reject traps" "—" \
  "Generate star systems from formation-inspired priors (star type, snow line, rock/ice/gas budgets). Orbits must be stable. Compute a difficulty metric; reject unsolvable templates (e.g. lone moonless gas giant). Support pre-game star pick with survey-level data." \
  "- [ ] Generates multi-body systems with stable orbits
- [ ] Feature priors depend on science-ish parameters (temp, distance, mass)
- [ ] Difficulty score computed
- [ ] Trap systems filtered or flagged
- [ ] Star pick receives survey summary")
A2N=${A2##*/}; echo "  A2 #$A2N"

A3=$(sub A3 "Orbital logistics: Δv orbit/escape, transfer options" "A1, A2 (#${A1N}, #${A2N})" \
  "Compute Δv to orbit and escape for bodies. For a haul order between bodies, produce real transfer options (e.g. low fuel / long TOF vs high fuel / shorter TOF) from orbital math, not balance fudge tables. Propellant is typed cargo; UI can show Δv." \
  "- [ ] Δv to orbit and escape available per body
- [ ] Haul planning returns at least two transfer options with fuel and months
- [ ] Costs derive from orbital model + ship mass
- [ ] Propellant consumed as cargo for burns")
A3N=${A3##*/}; echo "  A3 #$A3N"

A4=$(sub A4 "Tech/materials graph: atoms, processes, substitutes, ship fabs" "—" \
  "Data-driven tech book: atoms → processes → compounds/parts. Substitutes allowed with mass/efficiency penalties. Colony ship hosts tiny fabs (e.g. chips, foundry) with limited throughput. Full know-how known; geology and logistics gate feasibility." \
  "- [ ] Graph loads recipes and buildings from data
- [ ] At least one substitute path with a clear penalty
- [ ] Ship bootstrap fabs produce at capped rates
- [ ] Missing inputs block production (no free matter)")
A4N=${A4##*/}; echo "  A4 #$A4N"

A5=$(sub A5 "Goals → needs → contracts" "A4 (#${A4N})" \
  "Player authors a goal (e.g. plan a base with power/hab options). System expands the dependency graph into needs and contracts to fill. Not NPC quests. Multiple projects may target the same site." \
  "- [ ] Base/goal plan expands to concrete needs
- [ ] Needs become contracts/work packages
- [ ] Two projects can coexist on one site
- [ ] No auto-build on plan confirm")
A5N=${A5##*/}; echo "  A5 #$A5N"

A6=$(sub A6 "Actors: ship, scan sats, mining bots, haulers" "A3, A4 (#${A3N}, #${A4N})" \
  "Implement starting actors: colony ship, scanning satellites, asteroid mining bots, haulers. Scanning turns composition priors into measured deposits. Mining and hauling interact with contracts and orbital logistics." \
  "- [ ] Colony ship present at arrival with loadout
- [ ] Scan sats can survey bodies/sites
- [ ] Mining bots extract known deposits
- [ ] Haulers execute planned transfers")
A6N=${A6##*/}; echo "  A6 #$A6N"

A7=$(sub A7 "Web: star pick → transit → god's-eye system map" "A2, A3 (#${A2N}, #${A3N})" \
  "Web client: pre-game star selection, transit fast-forward to arrival, isometric/god's-eye system map showing bodies, orbits, and high-level assets. No mid-game galaxy UI; no NMS zoom." \
  "- [ ] Star pick UI with survey summary
- [ ] Transit/arrival flow
- [ ] System map renders bodies and orbits
- [ ] Can select a body to start a base plan")
A7N=${A7##*/}; echo "  A7 #$A7N"

A8=$(sub A8 "Vertical slice: one base plan + one physics haul E2E" "A1–A7" \
  "Wire milestone A end-to-end: arrive, plan one base, contracts appear, ship bootstrap feeds something, one haul uses real transfer options. This is the first playable definition." \
  "- [ ] Full solo path completable without cheats
- [ ] At least one contract filled via bootstrap and/or haul
- [ ] Transfer options shown and chosen for a haul
- [ ] Documented manual playtest steps")
A8N=${A8##*/}; echo "  A8 #$A8N"

A9=$(sub A9 "Persistence + solo colony room" "A1, A8 (#${A1N}, #${A8N})" \
  "Save/load colony state. Solo room: create and resume a game. Process lifecycle: if host/VPS process is down, room is offline; on wake, catch-up applies. Join-link stub optional for later MP." \
  "- [ ] Save and resume a colony
- [ ] Room create/resume works solo
- [ ] Catch-up runs after downtime
- [ ] State survives process restart")
A9N=${A9##*/}; echo "  A9 #$A9N"

A10=$(sub A10 "Design doc: v1 element/tech book" "— (parallel)" \
  "Science homework: author the v1 element list, key compounds, processes, drives, power sources, and base plan options. Planning-visible depth (medium): enough for CH₄ scoop + O₂ problem, iron→steel+power, chips as hard multi-input. Feeds A4 data." \
  "- [ ] Written tech/materials book in docs/
- [ ] Covers power ladder and at least two drive types
- [ ] Lists bootstrap ship modules and caps
- [ ] Notes formation→deposit priors mapping")
A10N=${A10##*/}; echo "  A10 #$A10N"

echo "Creating Milestone B issues..."
B1=$(sub B1 "Colony room join (link/code); light identity" "A9 (#${A9N})" \
  "Friends join a colony room via link or code. Light identity (display name). Self-host/VPS only; no public matchmaking." \
  "- [ ] Join via link or code
- [ ] Second client sees shared system state
- [ ] Light player identity
- [ ] No public browser/matchmaking required")
B1N=${B1##*/}; echo "  B1 #$B1N"

B2=$(sub B2 "Corps + asset claims" "B1 (#${B1N})" \
  "Corporations inside one shared colony. Corps can claim assets (mines, ships, factories). Claims are enforceable in the sim (not only social)." \
  "- [ ] Create/join a corp
- [ ] Claim and release assets
- [ ] Unclaimed vs claimed behavior defined
- [ ] Multiple corps in one colony")
B2N=${B2##*/}; echo "  B2 #$B2N"

B3=$(sub B3 "Contract fulfillment cross-corp; credits + barter" "A5, B2 (#${A5N}, #${B2N})" \
  "Any corp can fill contracts. Hybrid payment: colony credits and/or barter goods. Deadlines matter for delivery contracts." \
  "- [ ] Corp A can fill Corp B / settlement contract
- [ ] Credits and barter both supported
- [ ] Delivery by day Z evaluable
- [ ] Partial failure/breach state exists (even if simple)")
B3N=${B3##*/}; echo "  B3 #$B3N"

B4=$(sub B4 "Settlement demand estimates from structure" "A5, B3 (#${A5N}, #${B3N})" \
  "Sim estimates settlement needs from structure (pop, industry, farms, stockpile policy). Can seed contract suggestions from projected shortages." \
  "- [ ] Demand derived from settlement structure
- [ ] Projected shortfall visible
- [ ] Optional auto-suggested contracts from estimates")
B4N=${B4##*/}; echo "  B4 #$B4N"

B5=$(sub B5 "Shared calendar/alarms; multi-player vote-warp" "A1, B1 (#${A1N}, #${B1N})" \
  "Shared event calendar and alarms for all players in the room. Vote to accelerate to next event requires multi-player consent when multiple players are online." \
  "- [ ] Shared calendar visible to all
- [ ] Alarms shared or per-player as designed
- [ ] Vote-warp requires consent when 2+ online
- [ ] Solo still works without deadlock")
B5N=${B5##*/}; echo "  B5 #$B5N"

B6=$(sub B6 "Two-player playtest slice" "B1–B5" \
  "End-to-end co-op: one player runs supply (e.g. mining), another transport, base needs create contracts, route forms. Documented playtest." \
  "- [ ] Two players complete a co-op logistics loop
- [ ] Corps/claims used in the playtest
- [ ] Written playtest notes")
B6N=${B6##*/}; echo "  B6 #$B6N"

echo "Creating Milestone C issues..."
C1=$(sub C1 "Director: suggest goals from sim + tech graph" "A4, A5 (#${A4N}, #${A5N})" \
  "Colony Director AI reads known sim state and tech graph and suggests goals only (no free resources). Suggestions should be actionable (e.g. found ice base, close O₂ loop)." \
  "- [ ] Suggestions generated from real state
- [ ] No hallucinated deposits or free matter
- [ ] Suggestions map to existing goal types")
C1N=${C1##*/}; echo "  C1 #$C1N"

C2=$(sub C2 "Draft plan/contracts from suggested goal (confirm)" "C1 (#${C1N})" \
  "Accepting a Director suggestion drafts a plan and contracts through the same pipeline as human goals; player must confirm." \
  "- [ ] Accept → draft plan via same goals→needs→contracts path
- [ ] Confirm required before contracts go live
- [ ] Reject/dismiss works")
C2N=${C2##*/}; echo "  C2 #$C2N"

C3=$(sub C3 "Optional auto-corp / auto-director mode" "C2, B2 (#${C2N}, #${B2N})" \
  "Optional mode where AI can operate a corp / director to attempt to solve the system while the player watches. Must use legal actions only." \
  "- [ ] Auto mode can be enabled/disabled
- [ ] AI takes only legal sim actions
- [ ] System can progress without human input for a demo period")
C3N=${C3##*/}; echo "  C3 #$C3N"

C4=$(sub C4 "AI safety: no free resources; legal actions only" "C1–C3" \
  "Hard rules: Director/auto modes cannot spawn free resources, skip Δv, or ignore material requirements. Tests for cheat attempts." \
  "- [ ] Automated tests that AI cannot mint free mass/energy
- [ ] AI cannot complete transfers without fuel/Δv rules
- [ ] Documented safety constraints")
C4N=${C4##*/}; echo "  C4 #$C4N"

# Update umbrella with issue numbers
gh issue comment -R "$REPO" "$UMBRELLA_N" --body "$(cat <<EOF
## Created sub-issues

### Milestone A
- A1: #${A1N}
- A2: #${A2N}
- A3: #${A3N}
- A4: #${A4N}
- A5: #${A5N}
- A6: #${A6N}
- A7: #${A7N}
- A8: #${A8N}
- A9: #${A9N}
- A10: #${A10N}

### Milestone B
- B1: #${B1N}
- B2: #${B2N}
- B3: #${B3N}
- B4: #${B4N}
- B5: #${B5N}
- B6: #${B6N}

### Milestone C
- C1: #${C1N}
- C2: #${C2N}
- C3: #${C3N}
- C4: #${C4N}
EOF
)"

echo ""
echo "Done."
echo "Umbrella: $UMBRELLA_URL"
echo "A: #${A1N}-#${A10N}  B: #${B1N}-#${B6N}  C: #${C1N}-#${C4N}"
