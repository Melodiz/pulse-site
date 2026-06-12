# AI-Tech Field Pulse — Trends — 2026-06-10 (FIXTURE)

*Monthly trend review; window May 11 – June 10, 2026. Three tracked trends moved this
month. All content below is fictional fixture material for pipeline testing.*

## Trend updates

### T1 — SWE replacement: hiring freezes harden into structural cuts
Three more mid-cap SaaS companies announced engineering hiring freezes explicitly tied
to agentic coding rollouts, and one (fictional FlowStack) published a headcount plan
that holds engineering flat through 2027 while doubling product surface. The pattern
shift this month: freezes are being written into guidance, not just mentioned on
earnings calls. Attribution remains noisy — cost discipline still explains a large
share — but the direction is consistent.

### T7 — non-CUDA viability: second full post-train lands on Ascend
A second (fictional) lab-scale team reports completing full-parameter post-training of
a 700B-class open-weights model on an Ascend 910C cluster, replicating the DeepSeek V4
milestone at smaller scale and publishing intermediate loss curves. Pre-training a
frontier model from scratch on non-NVIDIA silicon remains undemonstrated. If a third
replication appears, this trend graduates from "watch" to "confirmed".

### T9 — AI-in-science throughput: first AI-primary paper clears peer review
A genomics paper whose experimental design, model training, and first-draft manuscript
were produced by an autonomous agent pipeline (fictional "HelixRunner") was accepted at
a mid-tier venue with human authors listed as supervisors. Reviewers were informed of
the AI-primary provenance. One acceptance is an anecdote, not a rate change — but it is
the first clean datapoint for this trend's headline question.

## Replacement state lines

T1 | SWE replacement | state: accelerating | confidence: medium | last-moved: 2026-06-10
T7 | non-CUDA viability | state: partially-confirmed | confidence: medium | last-moved: 2026-06-10
T9 | AI-in-science throughput | state: first-datapoint | confidence: low | last-moved: 2026-06-10

## Log block

RUN trends-2026-06-10 | 2026-06-10 | https://example.com/flowstack-headcount-plan | SWE replacement: freezes harden into structural cuts | trend |
RUN trends-2026-06-10 | 2026-06-10 | https://example.com/ascend-posttrain-replication | Non-CUDA viability: second Ascend post-train | infra |
RUN trends-2026-06-10 | 2026-06-10 | https://example.com/helixrunner-paper-accepted | AI-in-science: first AI-primary paper peer-reviewed | result |
