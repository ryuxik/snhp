# Attention design loop — viewer.html pass log

*Method: the loupe attention-loop skill (~/Desktop/loupe/.claude/skills/
attention-loop/SKILL.md) — declare each unit's intent, isolate by crop,
measure with DINOv2 saliency (`loupe/tools/ui_attention.py`), name the
measured-vs-intended gap as the defect, fix, re-measure, recurse. Shots:
headless Chrome at 1600×1000 on the σ=0.5 seed-0 demo pair, deep-linked to
tick 400 via the `t=` param (added for this loop).*

## North star for this surface

**The DEAL is the hero** — a barter arc + terms between two drones is the
one thing no auction visualization can show; the race score is the
shareable number. Drones/asteroids are cast, starfield is atmosphere,
chrome is quiet. (Analog of loupe's "photos are heroes": here the deals
change every frame and must WIN attention, not merely receive it.)

## Units & intents

- **U1 page** — two race panels dominate; header quiet.
- **U2 panel canvas** — deal arcs+captions = peak among dynamic elements;
  score findable; sites warm; starfield ~0.
- **U3 header bar** — play/scrub affordances findable (warm); title quiet.
- **U4 stats footer** — demoted to quiet chrome once the score moved
  in-canvas (intent revised in pass 2 — the footer's old job is done
  better by the in-field chip that screenshots/clips actually capture).

## Pass 1 (measure) — defects named

U1 bands 11–15% everywhere = uniform smear (the classic failure). Overlay:
- **D1** empty starfield patches as hot as content (stars alpha .25–.75
  fighting the fleet).
- **D2** the hero is illegible: deal arcs thin (1.3–2px) ghost lines;
  captions garbling text-on-text exactly at the dock hotspot.
- **D3** the race score = coldest band on the page (7.1% bottom band).
- **D4** scrub = brightest chrome (full-width cyan accent).

## Pass 2 (fix + re-measure)

Fixes: starfield 130→90 stars, alpha .10–.28; deal arcs 3px + glow
(shadowBlur 10), xfer arcs 1.6px + glow 4, ARC_FADE 24→32; captions
collected and drawn LAST with dark backing pills, collision-nudged into
vertical stacks, clutter-capped at 8, deals sorted first; in-canvas score
chip (amber, ~1.7-cell digits, top-left) per panel; scrub muted; play cyan.

Measured (U2 crop, left panel): **PASS** — the deal stack is the visible
attention peak; captions read cleanly ("4⚡ +swap", "1▣⇄4⚡", "1▣⇄8⚡");
asteroid clusters second; empty-space patches subordinate. Score chip is
DINOv2-cold — expected per the skill's flat-text caveat; judged by overlay
legibility instead: legible. U1: content peaks now sit on the deal zone;
footer band lowest (6.7%) which now MATCHES intent (U4 demoted).

## Pass 3 (header)

U3 visual judge (thin text unit → overlay/numbers uninformative per skill
caveat): native range track rendered near-white = brightest header element
(defect introduced by pass-2's accent change). Fixed with custom
webkit/moz track (4px, --line dark) + 12px cyan thumb. Re-shot: **PASS** —
play button + thumb are the only warm elements; title quiet.

## State

U1 PASS · U2 PASS · U3 PASS · U4 PASS (by demotion). Accepted residual:
DINOv2 keeps a mid-level texture floor on dark fields (empty-space
patches never reach 0); content peaks dominate, which is what intent
requires. Next recursion when the viz grows v4 features: per-company
refinery chips (two scores per panel), deal-pulse rings on the two robots
at strike tick, and a fresh U2 pass — new elements re-open the unit.
