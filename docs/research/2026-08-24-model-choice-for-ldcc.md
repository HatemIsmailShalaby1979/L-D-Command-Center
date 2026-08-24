# Research: Best quantized model (≤14B) for the L&D Command Center

Date: 2026-08-24 · Question: which local model (LM Studio or Ollama,
quantized, must fit hardware that caps around 14B/Q4) gives the best
results across OUR workload: journey/lesson-pack JSON generation,
translation fidelity (Language Lab), grammar explanations, podcast
dialogue, summaries/judging?

Method: developer discussions (r/LocalLLaMA), reproducible benchmarks with
published numbers (lector.dev COMET eval; TranslateBooksWithLLM wiki;
Modern DataTools gen bench; lostechies tool-call bench), and 2026 buyer
guides (InsiderLLM ×3, Intelligibberish VRAM tiers, betterclaw head-to-head,
MindStudio comparison, omarshabab.com bench). Sources inline.

---

## Verdict (for this app, not the general leaderboard)

| Role | Model | Size | Why |
|------|-------|------|-----|
| **Daily driver** | **Gemma 4 12B (QAT)** | ~6.6–7.5 GB Q4 | Tops the entire local field on translation COMET (statistically tied with frontier cloud); best instruction-following/format discipline of its class; proper tool calls out-of-box |
| **Long-form generator** | **Qwen 3 14B** (`think:false`) | ~9 GB | Crushes structured long-form content (avg 91/100 vs 54–62 for alternatives); perfect content-depth scores; this is the Journey/LessonPack/podcast-script engine |
| **Judge / verifier** | **Qwen 3.5 9B** | ~6.6 GB | Reasoning-heavy, output-light — exactly our verification-pass and grading-judge profile; community-documented strength at rubric→JSON verdicts |
| Optional MT specialist | TranslateGemma 12B | ~8.1 GB | Dedicated translator beating Gemma-3-27B baseline (MetricX 3.60 vs 4.04); Gemma licence terms apply |

One model is fine to start (Gemma 4 12B QAT); add Qwen 3 14B for heavy
generation days and Qwen 3.5 9B as the always-cheap checker.

## Evidence per claim

1. **Translation, local field**: lector.dev's blinded 24-model eval
   (COMET/chrF++, n=200×3 languages): `gemma-4-12b-qat` (7.5 GB) is "the
   same one sitting in the frontier band up top", leading German/Spanish
   among locals; gemma-3-12b within noise below it. Differences <1.5 COMET
   are declared sampling noise — read bands, not ranks.
   https://lector.dev/blog/local-llm-translation-eval/
2. **Qwen3-14B translation reality check**: hydropix's TranslateBooksWithLLM
   wiki ran `qwen3:14b` across 19 languages / 95 translations: average 6.0/10;
   Portuguese 7.4 > Spanish 6.8; Japanese 5.4 / Korean 5.6 weak.
   https://github.com/hydropix/TranslateBooksWithLLMs/wiki/Archive-Model-qwen3-14b
3. **Dedicated MT option**: Intelligibberish 2026 VRAM-tier guide:
   TranslateGemma 12B (Gemma-3-based, 55 langs, 8.1 GB Ollama tag) MetricX
   3.60 vs Gemma-3-27B baseline 4.04 — "strongest quality-per-gigabyte".
   Licence: Gemma Terms + Prohibited Use Policy (fine for personal use).
   https://intelligibberish.com/articles/2026-03-17-best-local-translation-models-2026-vram-tier-comparison/
4. **Long-form generation**: Modern DataTools benchmark: Qwen 3 14B averaged
   91/100 across topics with perfect content-depth sub-scores; Qwen 3.5 9B
   was inconsistent for generation (87 / 59 / zero-usable-words) —
   consistency beats peak performance.
   https://www.modern-datatools.com/blog/benchmarking-local-llms-qwen-model-comparison
5. **Judge/auditor fit**: same source: Qwen 3.5 9B excels at "read full
   text → evaluate against rubric → emit compact JSON verdict" — the exact
   shape of our P3.2-style verification passes.
6. **Instruction following & strict formats**: omarshabab.com 26-prompt
   bench (programmatic scoring): Gemma won instruction-following 4–0 vs
   Qwen 3.5; Qwen's thinking mode adds preambles that break strict formats.
   https://omarshabab.com/llm-benchmark/
7. **Tool calls / blank-response gotcha**: lostechies bench: `qwen3:14b`
   returns EMPTY responses unless `"think": false`; gemma4 ~12B behaves out
   of the box; phi4:14b rejects tools entirely (avoid Phi-4 here).
   https://lostechies.com/erichexter/2026/05/25/local-llm-bench-part-1-which-models-can-chat/
8. **Structured output guarantee**: InsiderLLM structured-output guide:
   LM Studio enforces `json_schema` via Outlines (token-level constraint);
   with constraints, "model quality matters less" for validity. Our
   Pipeline should adopt this (enhancement note below).
   https://insiderllm.com/guides/structured-output-local-llms/
9. **Multilingual breadth**: Qwen 3.5 family claims 201 languages
   (MindStudio comparison); Gemma 3 covered 140+, Gemma 4 skews
   English-centric per the same comparison — relevant only if the Language
   Lab targets non-European languages.
   https://www.mindstudio.ai/blog/gemma-4-vs-qwen-3-5-open-weight-comparison
10. **Community multilingual sentiment**: r/LocalLLaMA Qwen3-vs-Gemma3
    thread: several users report Gemma 3 12B beating Qwen3 14B in their
    languages; Qwen factual recall criticized.
    https://www.reddit.com/r/LocalLLaMA/comments/1kau30f/qwen3_vs_gemma_3/

## Implications for the app (actions, not just opinions)

1. **P7.1 capability profiles get concrete defaults**:
   daily-driver=Gemma-4-12B-QAT; generator=Qwen3-14B(think off);
   judge=Qwen3.5-9B; probe warns rather than blocks.
2. **Pipeline enhancement (new small task)**: send `response_format:
   json_schema` through LmStudioClient when LM Studio exposes it — turns
   schema-validity from "retry until lucky" into a guarantee; keep
   validators for SEMANTICS either way.
3. **Request-profile gotcha to encode**: any Qwen-3+ request must set
   thinking off (or budget for reasoning tokens) or outputs arrive empty —
   this belongs in client defaults, not user knowledge.
4. **Language Lab language guidance**: European pairs are safe on the
   daily driver; CJK wants Qwen-family models; low-resource pairs need
   dedicated MT (out of scope v1).

## Runner choice

LM Studio stays the default (already integrated, GUI, `json_schema`
support). Ollama is equivalent for these models (`format:` parameter,
same GGUFs) — nothing in the app depends on switching.

---

## Addendum (same day): ground truth — models actually on this machine

Scan method: full-tree GGUF/blob sweeps of both mounted NTFS volumes
(nvme0n1p2 = project drive, sda6 = apps/games), plus dotdir checks and an
attempted read-only mount of the unmounted 442 GB `sda4` (Windows C:).

Found:
- **Accessible volumes contain zero chat-model GGUFs.**
- **Confirmed via Modelfile** (`E2D6…/app/AI Automation Engineering/
  OllamaImports/local-agent-qwen3/Modelfile`): LM Studio store lives at
  `C:\Users\Thomas\.lmstudio\models`, containing at least
  **DeepSeek-R1-0528-Qwen3-8B Q4_K_M**, wrapped as Ollama
  `local-agent-qwen3` (num_ctx 4096, temp 0.2).
- **ComfyUI present** on sda6 with a MiniMax-Music-3 generation stack
  (dit Q6_K ~2.1 GB + text encoder ~9 GB + mmproj) — a ready-made asset
  for Phase 7's Playground media/music generation.
- C: could not be mounted read-only without admin rights (kernel ntfs3
  refused — typical hibernated-Windows protection).

Full enumeration therefore needs ONE of:
1. Windows side: `Get-ChildItem "$env:USERPROFILE\.lmstudio\models" -Recurse -Include *.gguf | Select FullName,@{n='GB';e={[math]::Round($_.Length/1GB,2)}}` and `ollama list`
2. Or approve here: `sudo mount -t ntfs-3g -o ro /dev/sda4 /mnt/win` then say "scan again".

Mapping to the verdict above: the one confirmed model (8B reasoning
distill) matches our **judge/checker** role, not the daily-driver role;
per §Verdict the pulls worth making are Gemma 4 12B QAT (driver) and
Qwen 3 14B (generation days).

## Addendum 2 (2026-08-24, later): COMPLETE enumeration — C: mounted via udisks

`sda4` mounted read-only first try through the desktop session
(`udisksctl mount -b /dev/sda4 -o ro` — polkit authorized it; no sudo,
no hibernation refusal this time because Windows was fully shut down).

Ground truth of `C:\Users\Thomas\.lmstudio\models` (every GGUF >50 MB):

| Model | File size | Notes |
|---|---|---|
| **gemma-4-12B-it-QAT Q4_0** (+ BF16 mmproj 0.16 GB) | 6.50 GB | **the recommended daily driver, already installed, vision-capable** |
| qwen-2.5-14b-instruct-1m Q4_K_M | 8.37 GB | fills the long-form generator slot (Qwen **2.5**, not 3; 1M-context variant) |
| Qwen2.5-7B-Instruct-Uncensored Q6_K | 5.82 GB | mid-size spare; fine for summaries/classification |
| granite-4.0-h-tiny Q4_K_M | 3.94 GB | ~7B-total/A1B-active MoE; lightweight summarizer |

Corrections to Addendum 1:
- **DeepSeek-R1-0528-Qwen3-8B has been DELETED** from the store since its
  Modelfile was written (`FROM` points at a path that no longer exists).
  No `.ollama` store exists under the user profile either (Ollama app is
  installed; `jcode/ollama.env` sets only a local-API flag). The "judge
  role" candidate from Addendum 1 is gone.
- Server logs (Aug 20) show the last load attempts were the MiniMax-
  Music-3 GGUFs into LM Studio — both failed (music DiT/mmproj are not
  chat models; they live correctly in the ComfyUI stack on sda6).

Caveat: the `AppData` sweep timed out mid-tree, so "nothing outside
`.lmstudio/models`" is unproven for C: — but no Ollama store, and the
store above matches settings.json's downloadsFolder.

Mapping to §Verdict (revised):
- **Daily driver: INSTALLED** (gemma-4-12B-it-QAT Q4_0). At 12B it clears
  every profile threshold in P7.1 except the >14B no-verify bar, so
  bilingual keeps its mandatory verification pass — by design.
- **Long-form generator: PARTIAL** — Qwen 2.5 14B 1M stands in for Qwen 3
  14B (`think:false` gotcha does not apply to 2.5; 1M ctx is useful for
  long transcripts). Pull Qwen 3 14B only if 2.5 disappoints on
  structured long-form.
- **Judge/verifier: MISSING** (DeepSeek-R1 distill deleted). Pull
  Qwen 3.5 9B when P7.3's model-judge lands; until then verification
  runs on the daily driver.
- Optional TranslateGemma 12B remains unpulled; Gemma 4 12B QAT's COMET
  band makes it low priority.
