# jev-android-mcp — generic on-device Android MCP + dual-tier agent (EN)

> `Jam` (`dev.jev.jam`) is a non-root Android app exposing UI via
> accessibility and actions via Shizuku to an MCP server on the PC. A
> dual-tier agent (S1 Jev + S2 LLM) executes natural-language goals through
> `run_goal(goal: str)`. Zero hardcoded apps in the core: specifics travel at
> runtime. Details: `PLAN.md`, `ARCHITECTURE.md`, `PROTOCOL.md`,
> `docs/specs/paradigm-shift.md`.

## What it is

- **Generic on-device Android MCP.** The Jam app reads the screen via
  `AccessibilityService` (`dump_ui` with `snapshot_id`), taps/types via
  gestures + `ACTION_SET_TEXT`, opens/stops apps and screenshots via Shizuku.
  The MCP server (Python + `uv`) maps that to atomic tools.
- **Dual-tier.** S1 Jev (TypeSafe, discriminative judgment in ms, no free
  text) resolves each step; S2 (frontier LLM) plans milestones, diagnoses,
  and composes text. Every goal enters via `run_goal(goal: str)`; for complex
  goals the director (operator) drives step by step with goal-blind
  `resolve_element` + API clipboard.
- **Secure by design.** No root, no `su`, `shell` OFF until Phase 6, explicit
  confirmation for critical actions, JSONL forensics per run.

## Architecture in 10 lines (+ diagram)

1. Jam serves 2 WS listeners: loopback `ws://127.0.0.1:38472` + tailnet-IP WSS.
2. `hello` with bearer token + scopes (`read`/`ui`/`shell`/`admin`).
3. Perception = accessibility tree (`dump_ui`, ≤500 nodes, ~2 ms/node).
4. Host normalizes and prunes (decor filtered) → numbered table 0..253 + NONE.
5. S1 Jev picks 1 primitive (`TAP/TYPE/SCROLL/BACK/DONE/ESCALATE`) + target.
6. S2 compiles (`EXECUTE_GOAL` + preloaded inputs) or directs (v5: operator).
7. Atomic mutation (`tap_node`/`type_text`/`open_app`) + post verification.
8. OS clipboard before fingers (`get` via host `dumpsys`, `set` via Jam API).
9. Audited costs (`[COST]` + `CostTracker`) and forensics `logs/run-<ts>.jsonl`.
10. No key → honest `{mock:true}` stub; options are never invented.

```
PC (Debian, uv, MCP stdio)              TECNO (Jam, non-root)
┌─ server.py: device/app/ui/jev ─┐      ┌─ ForegroundService: 2×WS ─┐
│ run_goal / director + S1 + S2  │─WS──▶│ Accessibility: tree+gest. │
│ normalizer, guards, cost, logs │◀─WS──│ Shizuku: am/monkey/screencap│
└────────────────────────────────┘      └───────────────────────────┘
  adb forward tcp:38472 │  WSS tailnet (opt-in, TOFU pinning)
```

## Quickstart

```bash
# 1. Install the APK and enable accessibility (once, on the phone)
adb install -r app/build/outputs/apk/debug/app-debug.apk
# Settings → Accessibility → enable Jam; generate the token in the app (QR).

# 2. The USER starts Shizuku (the app only requests the API_V23 runtime permission)
# Install the official moe.shizuku.privileged.api, start it, authorize Jam.

# 3. Forward + environment (on the PC)
adb forward tcp:38472 tcp:38472
cd mcp-server && cp ../.env.example ../.env   # edit: JEV_TOKEN, OPENROUTER_API_KEY, models
uv sync

# 4. Checks without Android Studio
uv run pytest -q                       # 127 green (v5 working tree)
cd ../android-app && ./gradlew :app:testDebugUnitTest

# 5a. Generic run_goal (simple case)
cd ../mcp-server
JEV_TOKEN=... OPENROUTER_API_KEY=... uv run python scripts/run_goal_check.py --goal "..."

# 5b. Step-by-step director (complex goal): per screen,
# read_screen_state → resolve_element("<micro EN of THIS screen>")
# → tap_idx/type_text/open_app → verification read → get/set_clipboard
# → forensics in logs/run-<ts>.jsonl. See docs/specs/director-client.md §9.4
# and Appendix A for the required report narrative.
```

## Security

- **Scopes:** `read` (dump/screenshot) · `ui` (tap/type/scroll/back, `open_app`
  grantless) · `shell` (grant-gated, OFF until Phase 6 → `METHOD_NOT_ALLOWED`) ·
  `admin` (token/audit). Token mandatory even on loopback; lockout 5 fails /
  60 s → 5 min; 4 MiB frame; 50 req/s (shell 5/s).
- **Confirm:** sending/communicating, buying/paying, deleting, account/
  permission changes, `shell`/adb are critical: without `confirm:true` they
  are planned without executing (`planned:true` + `preview` +
  `needs_confirm`); with it, execution + audit. No global blacklist
  (`forbidden?` opt-in per goal).
- **Forensics:** `logs/run-<ts>.jsonl` per step (phase, snapshot, `conf`/
  `tau`, `wire`, `cost`, `via`, hashes; never raw text when sensitive) plus
  fail-fast `run_signature` (2 equal deaths → do not relaunch).
- **Kill switch:** quick-settings tile + notification action (revoke tokens,
  stop server). Push/pull only under `/sdcard/Download/jev-mcp/`.

## Current status + roadmap

- **Today:** Phases 0–4 green; Phase 5 `run_goal` + v3/v4/§12 in working tree
  (127 pytest); v5 director-client in `docs/` + uncommitted `set_clipboard`;
  A10 suite measured (battery `88 %`, calculator with `avg_tap_ms 69.7`,
  `avg_s1_ms 1589.5`, costs <$0.003) but calculator-redo `ok_all: false`
  → B1 blocked by environment.
- **Roadmap:** certify A10 on KJ5 → close Jam `set_clipboard` + wrapper →
  P1 (anti-ticker signature, `assertFresh`, wire+timings forensics) → P2
  (relevance ranking + recalibrate `tau` with ≥20 goals) → Phase 6 (`shell`
  with denylist + grant + 500-audit + kill switch) → tailnet WSS 2b.
  Live detail in `PLAN.md`; turns in `docs/specs/paradigm-shift.md`.
