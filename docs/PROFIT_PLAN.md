# L&D Command Center — Profit Plan

> Owner directive (2026-09-05): a ruthless, profit-aiming plan that turns
> the existing project portfolio into independent, stable income. This
> document is the strategic source of truth; the tactical queue stays in
> TASKS.md.

## 0. The one unfair advantage

Every competitor (Duolingo, Babbel, LinkedIn Premium, resume builders)
pays per-token cloud bills and fights churn with ads. L&D Command Center
runs its entire brain — lesson generation, resume tailoring, cover
letters, job matching — on the user's own machine via LM Studio. That
means:

- **Zero marginal cost per user.** A thousand users cost the same as one.
- **Privacy as a product feature**, not a compliance checkbox. Career
  documents and learning history never leave the machine. This is a
  closing argument no SaaS resume tool can copy without losing revenue.
- **Offline works.** Job hunt from a plane, study on a metered connection.

Any monetization that breaks this advantage (cloud AI subscriptions,
data selling) is banned by CONSTITUTION-level principle. Monetize the
*software and the outcomes*, never the user's data or inference.

## 1. Focus ladder (what earns, in order)

The 2026-09-05 owner directive froze topic generation and audio
production (already shipped in Study Studio) to focus the app on three
money-facing pillars:

1. **Language Lab** — the uniquely competitive wedge.
2. **Career Development** — the highest willingness-to-pay wedge.
3. **Playground Paradise** — the retention and virality wedge.

The rule: every release must deepen 1 or 2, never spread thin.

### Why Language Lab wins the niche

Bilingual two-voice lesson packs with per-line audio, spaced repetition,
deterministic graders, and an inspectable fidelity audit — generated
locally for any topic in 15 languages — exist nowhere else at any price.
Duolingo gives one fixed curriculum; tutors charge $30-60/hour. L&D
gives a *personal curriculum for whatever the user actually needs to
say this week* (their field, their move, their interview).

### Why Career wins the pricing power

The full chain is one app: upload resume → import GitHub → connect
LinkedIn → enhance toward a role → watch job boards → prepare a full
application package (tailored resume PDF/DOCX + grounded cover letter +
listing reference) → draft human-sounding LinkedIn posts. The whole
"career campaign" loop, offline, for free, forever — then pay only for
convenience and depth.

## 2. Product ladder and pricing (ruthless version)

Three tiers, one executable, no accounts required to try anything:

| Tier | Price | What unlocks |
|---|---|---|
| **Free** | $0 forever | Full Language Lab (3 packs/week), 1 resume + 5 application packages total, job search, Playground, 10 E.T. voice turns/week, 3 writing evaluations/week, 1 level exam per level |
| **Pro** | $9/month or $79/year or $149 lifetime | **Unlimited E.T. voice conversations** + unlimited packs + SRS history, unlimited application packages, multi-resume profiles, LinkedIn post studio, unlimited writing evals + exam retakes, priority engines (queue packs while away) |
| **Campaign** (coaching-grade) | $29/month | Everything in Pro + "Career Campaign mode": the watchlist becomes a campaign manager — apply-tracking, follow-up letter generation, interview prep packs generated per listing |

Pricing psychology: the $149 lifetime anchors the $79/year as cheap and
gives the "no subscription" crowd an exit that is still 4x the yearly
price. The $9 tier exists to make $29 look serious, and Campaign is
where career-switchers (the highest-intent, highest-paying users) land.

**License mechanism:** offline-first license keys (signed token file in
storage/preferences). No phone-home, no account — matches the
constitution. Piracy risk is accepted; the audience (learners,
job-seekers) converts on trust, not enforcement.

## 3. Distribution — the funnel that costs nothing

1. **Content engine (biggest lever).** The app itself is a content
   factory: every lesson pack is a shareable interactive HTML file. Ship
   a "share/export pack" button → every shared pack is a landing page
   with a "made with L&D Command Center, free, offline" footer. Users
   who share study packs become the marketing department.
2. **GitHub open-core.** The engines stay MIT (they already are); the
   Pro tier ships as a closed binary. GitHub stars → Gumroad/own-site
   sales. The README already links the portfolio; make the L&D repo the
   storefront with a comparison table and a download CTA.
3. **The local-AI angle is the story.** "The language school + career
   coach that runs on your own laptop, no subscription AI" is a
   ready-made video/Reddit/HN hook. One 5-minute demo video (generate
   a Japanese lesson pack + prepare a full job application on camera,
   offline) does more than any ad budget.
4. **Niche communities, not broad ads.** r/languagelearning,
   r/cscareerquestions, expat forums (topic packs for "renting an
   apartment in Berlin" are the demo that converts expats), contact-
   center/CX career communities (the default job-board rosters already
   target this vertical — the app was tuned for it; own that niche
   first, then expand).

## 4. Revenue lines, ranked by expected stability

1. **Pro licenses (recurring core).** Target: 300 Pro users in 12
   months = $2.2k-2.6k MRR at $9 mix. Realistic with steady content
   output; modest, but stable and zero-cost.
2. **Campaign tier (high-ticket).** Career-switchers in the CX/contact-
   center niche. 30 users at $29 = $870 MRR. Small counts, big intent.
3. **Lesson Pack marketplace (post-v1).** Curated pack bundles
   ("Interview Japanese — tech", "Medical Spanish", "German for
   technicians") sold $4.99 each, 70/30 split to creators. Turns expert
   users into suppliers; the app becomes a platform. Requires the
   license/payment seam first — design for it now, build in v2.
4. **Institutional/white-label (the sleeping giant).** Language
   schools, bootcamps, outplacement firms, staffing agencies buy
   25-seat site licenses at $499-999/year. The pitch: unlimited local
   generation, student data never leaves the lab machines. One deal
   equals a hundred Pro users. Outplacement firms *already* charge
   job-seekers; give them a differentiator.
5. **Sponsored pack channels (optional, guarded).** A school or tutor
   can publish branded packs (logo in the HTML footer). Sell
   placement, never data, never ads inside lessons.

## 5. Using the existing portfolio (assets on hand)

- **Study Studio** — owns topic generation, audiobooks, podcasts (the
  frozen features). Position it as the *study/media companion app*;
  cross-sell: every Study Studio install shows "Need a language or a
  job? L&D Command Center" and vice versa. Two apps, one funnel, zero
  overlap after the 2026-09-05 freeze.
- **Helix Education / Helix Prime** — the governed core and the
  education platform story. Institutional buyers (line 4) land on
  Helix; L&D ships as the desktop client. The portfolio reads as a
  coherent ecosystem to a school procurement officer, which is exactly
  what closes site licenses.
- **Portfolio repo** — the storefront. One page: the apps, the demo
  video, the buy links, the license tiers.

## 6. Ninety-day execution ladder

**Days 1-30 (while the app hardens):**
- Ship the 2026-09-05 focus build (done this session): 7B-14B format
  wall removed, career memory, async UI, frozen sections.
- Record the 5-minute offline demo video. Publish the README store
  page with tier table.
- Set up Gumroad (fastest start; move to own checkout when volume
  justifies it). Lifetime launch price $99 for the first 100 keys —
  "founder keys" convert the earliest audience and fund the roadmap.

**Days 31-60:**
- License key seam + Pro feature gates (pack counter, resume profile
  limits) — all offline-verifiable.
- Share/export button on lesson packs (the growth loop).
- 10 curated flagship packs per top-3 language (es, ja, de) as free
  marketing artifacts, each footered with the app.

**Days 61-90:**
- Campaign mode v0 (apply-tracking + interview prep pack generation
  per listing — the $29 tier's reason to exist).
- First outreach round to 20 language schools and 10 outplacement /
  staffing firms with a 30-day pilot offer.
- Review numbers: if Pro conversion < 1% of installs after 5k
  installs, pivot weight to institutional (line 4) — the product is
  already strong enough for B2B demos.

## 7. Non-goals (the ruthless part)

- No cloud inference tier, ever. It breaks the cost moat and the
  privacy promise.
- No freemium dark patterns: the free tier stays genuinely useful.
  Trust is the brand; a crippled free tier kills the funnel.
- No marketplace before the license seam exists (v2, not v1.5).
- No new features outside the three focus pillars until Pro MRR covers
  a coffee-per-day baseline (the signal that focus is working).
- No paid ads. The content loop + niche communities + institutional
  outreach are the only channels until revenue says otherwise.

## 8. Honest risk register

- **Model dependency:** users must run LM Studio. Mitigated by the
  capability probe + the size-aware policy (this session) — but v1.1
  should bundle a "tiny model quick-start" that downloads one
  known-good 7B model on first run.
- **Piracy:** lifetime keys get shared. Accepted — the goal is
  adoption first, and institutions pay regardless.
- **Solo-operator bandwidth:** the 90-day ladder assumes ~part-time
  execution. If content output stalls, drop the marketplace plans and
  protect the funnel (shareable packs + demo video).
- **Payment friction:** Gumroad solves checkout but takes 10%+. Fine
  until $1k MRR; then own checkout.

## 9. The single success metric

**Pro+Campaign MRR per active installer.** Not installs, not stars.
Every product decision from here is judged by whether it moves a user
from free → Pro (Language Lab depth) or Pro → Campaign (career
outcomes). Ship nothing that doesn't.

## 10. Project E.T. — the Pro headline (added 2026-09-06)

The live voice conversation partner (Mr. & Mrs. E.T.), the A1→C1
curriculum library, level exams, and the Skills Arena are the
strongest Pro upgrade drivers in the product — speaking practice is
what tutors charge $30-60/hour for, and nobody offers it offline:

- **Free tier gets a real taste**: one full short conversation per
  week with E.T. (10 turns), 3 writing evaluations, one exam shot
  per level — enough to fall in love, not enough to never pay.
- **Pro = "unlimited conversations with your alien tutor"** — the
  cleanest one-line upgrade pitch in the funnel. The $149 lifetime
  vs. a single month of human tutoring is the demo-video close.
- **Marketing engine**: the E.T. demo (record → get corrected live →
  hear the alien reply, all offline) is the Days 1-30 video; every
  shared flagship pack footers straight into the funnel.
- **Institutional angle**: schools buy exactly this — unlimited
  local speaking practice with automatic rubric grading, student
  audio never leaving the lab machine.

---
UPDATE 2026-09-23 — Endpoint auto-detect (ollama/LM Studio) applied; quality guard (non-robotic + humor/tips) active; e2e smoke report: E2E_SMOKE_REPORT.md. Release judgment: small boring change shipped; rollback via previous archive in build/.