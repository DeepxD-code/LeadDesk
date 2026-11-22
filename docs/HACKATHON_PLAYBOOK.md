# What actually wins a hackathon — and where LeadDesk stands

Research pass, consolidated. Sources: Devpost's judge interviews, a hackathon-rubric survey (mapdevents /
scorejudge / theinnovationmode), and winning-team write-ups. The goal was not general advice but a checklist we can
score ourselves against.

---

## 1. The rubric is public, and winners aim at it explicitly

Judges converge on the same six axes. Typical weights:

| Criterion | Weight | The judge's actual question |
|---|---|---|
| Technical execution | 25% | Does it really work, or is the demo faked? |
| Innovation / originality | 20% | Would I have thought of this? |
| Impact / usefulness | 20% | Would this matter if shipped? |
| Design / UX | 15% | Could a real user pick it up? |
| Completeness | 10% | End-to-end flow, or a screenshot and a promise? |
| Presentation | 10% | Did they explain it well in the time given? |

The single most repeated judge comment: *"surprising how many submissions did not fulfil the basic requirements."*
Covering every stated requirement **visibly** is a cheap, large score.

## 2. What winners do that most teams do not

1. **They demo the hard thing, not the CRUD.** The "wow" is the technical hurdle that was actually conquered. List
   screens impress nobody.
2. **They record the demo and narrate live over the recording.** Live demos fail in front of judges. With a
   non-deterministic LLM, a recording of a good run is strictly better than gambling.
3. **They bring numbers.** The classic dry-run feedback is *"you're missing numbers"*. Exec judges respond to hours
   saved, cost per seat, error reduction — quantified, even if modelled.
4. **They rehearse the Q&A.** Winners prepare the hostile questions in advance ("what stops this being a GPT wrapper?",
   "how is this different from a wiki search?") and answer them in one sentence.
5. **They scope ruthlessly.** Everyone advises the same thing: get one path working A→Z, and put every extra idea on a
   "what's next" slide instead of building it. Edge cases and scale are explicitly *not* hackathon work.
6. **They tell a story.** Judges see the video first and often judge the story before the code. A named user, a concrete
   failure, then the fix.
7. **They are visually distinctive.** The bar is "not a default template". Distinction is remembered when a judge is
   comparing 40 tabs.

## 3. What judges are tired of

- **GPT wrappers.** A chat box over an API is now the default submission. Judges explicitly reward the opposite:
  local models, determinism, real cryptography, concurrency control, evaluation.
- **Fake demos.** Anything that turns out to be mocked reads as deceit and sinks the whole entry.
- **Ambitious and broken.** Completeness beats scope. A working 3-feature app beats a broken 8-feature one.

---

## 4. Scorecard: LeadDesk against that checklist

| What wins | LeadDesk today | Verdict |
|---|---|---|
| Real technical difficulty on display | AES-256-GCM envelope encryption, hash-chained append-only audit, `BEGIN IMMEDIATE` + partial unique index race guard, TF-IDF retrieval with an answer gate | **Strong** — and genuinely uncommon |
| Local AI, not a wrapper | Ollama on the host, nothing leaves the machine, extractive fallback when offline | **Strong** |
| Honest failure | Unanswerable questions go to the lead instead of being invented | **Strong** — judges like this |
| Evidence, not claims | "How we know it works" panel: live eval, chain verification, ciphertext proof, race simulation | **Strong** |
| Numbers / impact | Not quantified anywhere | **Missing** |
| Deterministic demo | No guided path; depends on a live model being warm | **Weak** |
| Multilingual (Hindi/Gujarati) | 0/2 right now | **Broken** |
| Accuracy with no model installed | 4/5 | **Weak** — a cold judge machine demos worse |
| Requirement traceability | Requirements are met but not *shown* as met | **Missing** |
| Pitch assets | README only; no screenshots, diagram, script, Q&A | **Missing** |
| Polish / distinctiveness | Clean product UI, but no landing impression | **Adequate** |

## 5. The plan this produces

In order, each one independently worth points:

1. **Multilingual actually works** — Hindi/Gujarati question, English SOP source, no model required.
2. **5/5 with no model installed** — the demo must be identical on a cold judge laptop.
3. **Guided demo mode** — one path A→Z in three minutes, deterministic, with the wow moments on buttons.
4. **Numbers** — hours saved per week computed from real seed data, shown in-product, not asserted in a slide.
5. **Requirement traceability matrix** — every brief bullet → where it lives → how to prove it in one click.
6. **Pitch assets** — screenshots, architecture diagram, 3-minute script, hostile Q&A.
7. **Record the demo** — a video of a good run, as insurance.

Items 1–2 are engineering. 3–4 are product. 5–7 are submission. Nothing here adds a new feature the brief did not ask
for — the brief's own "what's next" list stays on the "what's next" slide, as the research says it should.
