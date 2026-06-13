# Pulse Log
 
One line per surfaced item. Claude emits these in each pass's log block;
Ivan pastes them here and later fills feedback for items that mattered.
 
Line format:
RUN | DATE | link | short item | type (MODEL/NEWS/MODALITY/TREND) | feedback
Feedback: 👍 or 👎 + ≤10 words on why. Blank = no opinion yet.
Run IDs: N<week> for news passes (N1, N2, ...), TR<n> for trend passes
(TR1, TR2, ...).
 
Size rule: when this file exceeds ~150 lines, move the oldest runs to
ARCHIVE_pulse_log_<range>.md, leaving one line per archived run with just
the links/IDs (dedup keeps working, attention cost stays low).
 
--- log starts ---
N1 | 2026-06-09 | anthropic.com/news/claude-fable-5-mythos-5 | Fable 5 + Mythos 5: new Mythos tier above Opus; strong hard-impl evidence (Wiegold/Shipper/Vals) | MODEL | 
N1 | 2026-06-09 | interconnects.ai/p/claude-fable-5-and-new-ai-safety | Fable 5 silently degrades "frontier LLM dev" via steering/PEFT, no user notice — workflow integrity flag | MODEL | 
N1 | 2026-06-04 | anthropic.com/institute/recursive-self-improvement | "When AI builds itself": Claude authors >80% of Anthropic code; coordinated-pause proposal | NEWS | 
N1 | 2026-05-28 | anthropic.com/news/claude-opus-4-8 | Opus 4.8: honesty/reliability upgrade, Dynamic Workflows (≤1000 subagents) | MODEL | 
N1 | 2026-06-09 | the-decoder.com/anthropic-releases-claude-fable-5-and-mythos-5 | Mythos 5 autonomous genomics result — Anthropic-reported, unpublished → T9 | NEWS | 
N1 | 2026-04-24 | tomshardware.com/news/huawei-led-team-claims-it-post-trained-deepseeks | DeepSeek V4 post-trained on Huawei Ascend cluster — post-training only, disputed → T7/T5 | NEWS | 
N1 | 2026-06-09 | bloomberg.com/news/articles/2026-06-09/google-s-backstops-underpin-35-billion-chip-deal-for-anthropic | $35B Apollo/Blackstone deal, Google-TPU-backed; expands Anthropic capacity | NEWS | 
N1 | 2026-06-02 | cybersecuritydive.com/news/trump-ai-security-executive-order/821755 | Trump EO: 30-day govt pre-release access to frontier models, voluntary → T6 | NEWS | 
N1 | 2026-03-20 | technologyreview.com/2026/03/20/1134438 | OpenAI auto-researcher roadmap (intern Sep'26 / full Mar'28) — plan only → T2 | NEWS |