# ElevenLabs levers for human-sounding narration — and what this repo already does

Research date: **2026-08-19**. All Part 1 claims were read from the live ElevenLabs
documentation on that date (raw markdown via `https://elevenlabs.io/docs/<path>.md`).
All Part 2 claims were read from the actual source files in this repo; every claim
carries a `file:function` reference.

Legend used throughout:

| Mark | Meaning |
|---|---|
| **DOC** | Stated explicitly in official ElevenLabs documentation, with the URL given |
| **DOC-EX** | Demonstrated in an official docs code example but never stated as a rule |
| **FOLK** | Widely repeated but **not** found in official docs on 2026-08-19 |
| **UNVERIFIED** | Could not be confirmed either way from this container (no API key, no live calls) |

> **No live API calls were made.** There is no `ELEVENLABS_API_KEY` in this container and
> no generation was performed. Everything about actual audible behaviour is documentation
> plus this repo's own recorded measurements, not fresh measurement.

---

# PART 1 — What levers exist

## 1. Models available (2026) and long-form trade-offs

Source: <https://elevenlabs.io/docs/overview/models> ·
<https://elevenlabs.io/docs/eleven-api/choosing-the-right-model> ·
<https://elevenlabs.io/docs/help-center/technical/what-models-do-you-offer-and-what-is-the-difference-between-them>

| Model ID | Languages | Char limit / request | Latency | Long-form narration verdict | Status |
|---|---|---|---|---|---|
| `eleven_v3` | 70+ (docs say "70+"; the help-center article says 74) | **5,000** (~5 min) | High | Docs call it "Perfect for long-form narration with complex emotional delivery" — but it is also called "more variable consistency" | Flagship |
| `eleven_v3` Conversational | 70+ | not stated | ~280 ms | Realtime/agents, not narration | Flagship; **model id not published in the models table — UNVERIFIED** |
| `eleven_multilingual_v2` | 29 | **10,000** (~10 min) | Standard | **"Most stable on long-form generations"** — the docs' own phrase | Flagship |
| `eleven_flash_v2_5` | 32 | **40,000** (~40 min) | ~75 ms† | Cheap and fast; weak number normalization; lower quality ceiling | Flagship |
| `eleven_flash_v2` | en | 30,000 (~30 min) | ~75 ms† | English only; **the only model that still accepts SSML `<phoneme>` tags** | Flagship |
| `eleven_turbo_v2_5` | 32 | 40,000 | ~250–300 ms | — | **Deprecated**, replace with `eleven_flash_v2_5` |
| `eleven_turbo_v2` | en | 30,000 | ~250–300 ms | — | **Deprecated**, replace with `eleven_flash_v2` |

† excluding application and network latency.

**Turbo v2.5 is dead as a recommendation.** DOC: *"The `eleven_turbo_v2_5` and
`eleven_turbo_v2` models are functionally equivalent to the `eleven_flash_v2_5` and
`eleven_flash_v2` models respectively, except the latency on the Flash models is lower on
average. We recommend using the Flash models over Turbo models in all use cases."*

### A live contradiction in the docs — flag this before any model swap

Two official pages disagree about which model to use for content creation:

- `/docs/overview/models#model-selection-guide` → **Content creation: use
  `eleven_multilingual_v2`** — *"Ideal for professional content, audiobooks & video narration."*
- `/docs/eleven-api/choosing-the-right-model` → **Content creation: use `eleven_v3`** —
  *"Ideal for professional content, audiobooks, and video narration."* (identical sentence,
  different model)

The same two pages also disagree on "Quality" (`eleven_multilingual_v2` vs `eleven_v3`) and
on "Multilingual". **DOC on both sides; unresolvable from the docs.** For a channel whose
whole requirement is a consistent read across 12 minutes, the tiebreakers are the
non-contradicted facts: multilingual v2 is described as *"Most stable on long-form
generations"*, v3 is described as having *"more variable consistency"*
(<https://elevenlabs.io/docs/help-center/product/core-capabilities/text-to-speech/what-is-eleven-v3-alpha>),
and **request stitching does not work on v3 at all** (see §5).

### What each model supports

| Capability | v3 | multilingual_v2 | flash_v2_5 | flash_v2 |
|---|---|---|---|---|
| Audio tags (`[whispers]` etc.) | **Yes** | No | No | No |
| SSML `<break time="x.xs" />` | **No** (DOC, explicit) | Yes | Yes | Yes |
| SSML `<phoneme>` tags | No (uses inline IPA instead) | No — "skipped", silently | No | **Yes, only model** |
| Inline IPA `/…/` | **Yes**, 80–90% consistency | No | No | No |
| Request stitching (`previous_request_ids`) | **No** (DOC, explicit) | Yes | Yes | Yes |
| `speed` voice setting | **No** | Yes | Yes | Yes |
| `similarity_boost` | **No** | Yes | Yes | Yes |
| `use_speaker_boost` | **No** | Yes | Yes | Yes |
| `style` | Yes | Yes | Yes | Yes |
| Text normalization by default | — | Good ("$1,000,000" → "one million dollars") | **Off by default**; Enterprise-only to enable on v2.5 | weak |
| Pronunciation dictionaries (alias tags) | Yes | Yes | Yes | Yes |

Sources: <https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices> ·
<https://elevenlabs.io/docs/eleven-creative/playground/text-to-speech> ·
<https://elevenlabs.io/docs/eleven-api/guides/how-to/text-to-speech/request-stitching>

**The single biggest structural fact for this repo:** v3 buys audio tags and gives up
request stitching, `speed`, `similarity_boost` and `use_speaker_boost` — four things the
ExplainTory pipeline currently relies on (see Part 2 §7).

---

## 2. v3 audio tags — the documented inventory

Primary source: <https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices#prompting-eleven-v3>
(also served at `/docs/best-practices/prompting/eleven-v3`).

### 2a. Tags listed as inventory in the prompting guide

| Tag | Category | Status |
|---|---|---|
| `[laughs]`, `[laughs harder]`, `[starts laughing]`, `[wheezing]` | Voice-related | **DOC** |
| `[whispers]` | Voice-related | **DOC** |
| `[sighs]`, `[exhales]` | Voice-related | **DOC** |
| `[sarcastic]`, `[curious]`, `[excited]`, `[crying]`, `[snorts]`, `[mischievously]` | Voice-related | **DOC** |
| `[gunshot]`, `[applause]`, `[clapping]`, `[explosion]` | Sound effects | **DOC** |
| `[swallows]`, `[gulps]` | Sound effects | **DOC** |
| `[strong X accent]` (X = accent) | Unique/special | **DOC**, marked experimental |
| `[sings]`, `[woo]`, `[fart]` | Unique/special | **DOC**, marked experimental |

### 2b. Tags listed in the official "Enhance" LLM prompt (published verbatim in the same docs page)

This is the prompt ElevenLabs' own UI "Enhance" button runs. It is official text, but the
docs label the list *"Non-Exhaustive"*.

| Tag | Category | Status |
|---|---|---|
| `[happy]`, `[sad]`, `[excited]`, `[angry]`, `[whisper]`, `[annoyed]`, `[appalled]`, `[thoughtful]`, `[surprised]` | Directions | **DOC** |
| `[laughing]`, `[chuckles]`, `[sighs]`, `[clears throat]` | Non-verbal | **DOC** |
| **`[short pause]`, `[long pause]`** | Non-verbal | **DOC** — the only documented *named* pause tags for v3 |
| `[exhales sharply]`, `[inhales deeply]` | Non-verbal | **DOC** |
| `[standing]`, `[grinning]`, `[pacing]`, `[music]` | — | **DOC as forbidden**: *"DO NOT use tags such as…"* |

Also from the help centre
(<https://elevenlabs.io/docs/help-center/product/core-capabilities/text-to-speech/how-do-audio-tags-work-with-eleven-v3-alpha>,
<https://elevenlabs.io/docs/help-center/product/core-capabilities/text-to-speech/what-is-eleven-v3-alpha>):
`[curious]` `[crying]` `[mischievously]` `[whispers]` **`[shouts]`** `[laughs]`
`[clears throat]` `[sighs]` `[sad]` `[angry]` `[happily]`. **DOC.**

And for breathing specifically
(<https://elevenlabs.io/docs/help-center/product/core-capabilities/text-to-speech/can-you-make-voices-produce-the-sound-of-breathing>):
*"With Eleven v3, you can use audio tags such as `[sighs]` or `[exhales]` to add breathing…"*. **DOC.**

### 2c. Tags that appear only inside official examples (DOC-EX)

These are in the docs' own sample scripts but are never listed as supported. They are
better evidence than a forum post and worse evidence than the tables above:

`[frustrated sigh]`, `[happy gasp]`, `[sigh]`, `[pauses]`, `[pause]`, `[pause, then normally]`,
`[dismissive]`, `[cute]`, `[giggles]`, `[giggling]`, `[laughing hysterically]`,
`[with genuine belly laugh]`, `[singing quickly]`, `[strong French accent]`,
`[strong Russian accent]`, `[professional]`, `[sympathetic]`, `[questioning]`,
`[reassuring]`, `[robotic voice]`, `[binary beeping]`, `[nervously]`, `[alarmed]`,
`[sheepishly]`, `[stifling laughter]`, `[cracking up]`, `[desperately]`, `[panicking]`,
`[deadpan]`, `[warmly]`, `[amazed]`, `[delighted]`, `[impressed]`, `[dramatically]`,
`[curiously]`, `[excitedly]`, `[cautiously]`, `[starting to speak]`, `[jumping in]`,
`[overlapping]`, `[interrupting, then stopping abruptly]`, `[sighing]`, `[muttering]`.

### 2d. What the docs actually say about reliability

| Claim | Verbatim | Status |
|---|---|---|
| Tag effectiveness is voice-dependent | *"The voice you choose and its training samples will affect tag effectiveness. Some tags work well with certain voices while others may not. Don't expect a whispering voice to suddenly shout with a `[shout]` tag."* | **DOC** |
| Voice choice is the dominant parameter | *"The most important parameter for Eleven v3 is the voice you choose."* | **DOC** |
| Experimental tags are inconsistent | *"Some experimental tags may be less consistent across different voices. Test thoroughly before production use."* | **DOC** |
| Tags must match voice character | *"Use tags intentionally and match them to the voice's character. A meditative voice shouldn't shout; a hyped voice won't whisper convincingly."* | **DOC** |
| Beyond-list tags may work | *"There are likely many more effective tags beyond this list. Experiment with descriptive emotional states and actions."* | **DOC** |
| Tags can be combined | *"You can combine multiple audio tags for complex emotional delivery."* | **DOC** |
| PVCs are weak on v3 | *"Professional Voice Clones (PVCs) are currently not fully optimized for Eleven v3… it would be best to find an Instant Voice Clone (IVC) or designed voice"* | **DOC** |

### 2e. What the docs do **not** say — flag these as folklore

| Common claim | Status |
|---|---|
| "Don't use more than N audio tags per generation / overuse degrades output" | **FOLK.** The overuse warning in the docs is about **`<break>` tags**, not audio tags. No overuse limit for audio tags was found anywhere on 2026-08-19. |
| "Audio tags at the start of a line are stronger than mid-line" | **FOLK.** The Enhance prompt says place them *"immediately before the dialogue segment they modify or immediately after"* — no strength claim. |
| "Unrecognised tags are silently dropped" | **FOLK / UNVERIFIED.** Not stated. The opposite behaviour *is* documented for non-v3 models (see below). |
| "Tags are free / not billed" | **FOLK.** No exemption is documented; billing is per character of `text` (§7). |
| Any specific numeric duration for `[short pause]` / `[long pause]` | **FOLK.** Never quantified. |

**A documented failure mode people forget:** on non-v3 models, emotional/descriptive text is
**spoken aloud**. DOC: *"Explicit dialogue tags yield more predictable results than relying
solely on context, however the model will still speak out the emotional delivery guides.
These can be removed in post-production."* and *"Descriptive text will be spoken out by the
model and must be manually trimmed or removed from the audio if desired."*
(<https://elevenlabs.io/docs/overview/capabilities/text-to-speech>). So dropping `[whispers]`
into an `eleven_multilingual_v2` request is not a no-op — it is a risk of the words being read.

---

## 3. Pause control

### 3a. `<break time="x.xs" />`

Sources: <https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices#pauses> ·
<https://elevenlabs.io/docs/help-center/product/core-capabilities/text-to-speech/how-can-i-add-pauses>

| Fact | Verbatim / value | Status |
|---|---|---|
| Syntax | `<break time="1.5s" />` | **DOC** |
| Max length | *"The AI can handle pauses of up to 3 seconds"* / *"for natural pauses up to 3 seconds"* | **DOC** |
| Units | *"Break time should be described in seconds."* | **DOC** |
| Which models | *"the most consistent way to add a pause on **Multilingual v2, Flash v2, and Flash v2.5**"* | **DOC** |
| **Not** on v3 | *"Eleven v3 does not support SSML break tags."* (stated twice, in two places) | **DOC** |
| It is not inserted silence | *"It is not just inserted silence between words—the model understands the syntax and adds a natural pause."* | **DOC** |
| Overuse breaks things | *"Using too many break tags in a single generation can cause instability. The AI might speed up, or introduce additional noises or audio artifacts. We are working on resolving this."* | **DOC** |
| **Maximum number per request** | — | **FOLK.** No number is published. "Max 3 breaks per generation" is a community figure, not a documented one. |
| Voice-dependent behaviour | *"Different voices may handle pauses differently, especially those trained with filler sounds like 'uh' or 'ah.'"* — such voices may insert those sounds during the pause | **DOC** |
| Breaks being silently ignored | — | **FOLK / UNVERIFIED.** Widely reported; not documented. |

### 3b. Punctuation-driven pauses

| Device | What the docs say | Status |
|---|---|---|
| Dash `-` / em-dash `—` | *"A simple dash `-` or the em-dash `—` often works well."* Example: `"It - is - getting late."` | **DOC** |
| Multiple dashes `-- --` | *"You can add multiple dashes such as `-- --` for a longer pause."* | **DOC** |
| Ellipsis `...` | *"can sometimes add a pause between words, but it usually also adds some hesitation or nervousness to the voice that might not always fit."* For **v3**: *"Ellipses (...) add pauses and weight."* | **DOC** |
| Capitalisation | v3: *"Capitalization increases emphasis."* | **DOC** |
| Quotation marks | *"Add emphasis by putting the relevant words or phrases in quotation marks."* | **DOC** |
| Standard punctuation generally | v3: *"Standard punctuation provides natural speech rhythm."* / *"Punctuation and voice settings play the leading role in how the output is delivered."* | **DOC** |
| Relative reliability | *"These options are less consistent than break tags or audio tags"* / *"Alternatives to `<break>` include dashes… However, these are less consistent."* | **DOC** |
| **Comma → a specific pause length (ms)** | — | **FOLK.** No duration is documented for any punctuation mark. Every "a comma gives ~200 ms" figure is measurement, not documentation. |
| **Period vs comma vs ellipsis relative lengths** | — | **FOLK.** |
| **Single newline vs blank line / paragraph break affecting timing** | — | **FOLK.** The docs never mention line breaks or paragraph breaks as timing controls at all. The nearest DOC statement is v3's *"Text structure strongly influences output with v3."* — which asserts influence without specifying it. |
| Narrative style as a pacing device | *"Write prompts in a narrative style, similar to scriptwriting, to guide tone and pacing"*; *"Pacing can also be controlled by writing in a natural, narrative style."* | **DOC** |

**Conclusion for a pause layer:** the only *documented, quantified* pause primitive is
`<break time="…s" />`, it caps at 3 s, it is unavailable on v3, and it destabilises when
overused with no published threshold. Everything about punctuation timing is qualitative.
Deterministic silence inserted at stitch time (which is what this repo already does — Part 2
§3) is the only pause mechanism with an exact, repeatable duration.

---

## 4. Voice settings

Authoritative parameter reference: <https://elevenlabs.io/docs/api-reference/text-to-speech/convert>
(request body → `voice_settings`). Behavioural descriptions:
<https://elevenlabs.io/docs/eleven-creative/playground/text-to-speech#voice-settings>.

| Field | Type | Range | Default | What it does (DOC) |
|---|---|---|---|---|
| `stability` | double | 0.0–1.0 | **0.5** | *"Determines how stable the voice is and the randomness between each generation. Lower values introduce broader emotional range… Higher values can result in a monotonous voice with limited emotion."* Too low → *"odd performances that are overly random and cause the character to speak too quickly."* |
| `similarity_boost` | double | 0.0–1.0 | **0.75** | *"Determines how closely the AI should adhere to the original voice."* Too high on a poor source → *"the AI may reproduce artifacts or background noise."* |
| `style` | double | 0.0–1.0 | **0.0** | *"Determines the style exaggeration of the voice… It does consume additional computational resources and might increase latency if set to anything other than 0."* And: *"using this setting has shown to make the model slightly less stable."* Docs: ***"In general, we recommend keeping this setting at 0 at all times."*** |
| `use_speaker_boost` | boolean | — | **true** | *"Boosts the similarity to the original speaker. Using this setting requires a slightly higher computational load, which in turn increases latency."* *"The differences introduced by this setting are generally rather subtle."* |
| `speed` | double | see below | **1.0** | *"values less than 1.0 slow down the speech, and values greater than 1.0 speed it up."* |

### The `speed` range is contradicted across official sources — flag before use

- Product docs & help centre: **0.7 minimum, 1.2 maximum**. *"Values below 1.0 will slow the
  voice down, to a minimum of 0.7. Values above 1.0 will speed up the voice, to a maximum of
  1.2. Extreme values may affect the quality."*
  (<https://elevenlabs.io/docs/help-center/product/core-capabilities/text-to-speech/can-i-change-the-pace-of-the-voice>)
- API reference: no min/max published at all, only `default: 1`.
- ElevenLabs' own published agent skill
  (<https://github.com/elevenlabs/skills/blob/main/text-to-speech/references/voice-settings.md>):
  *"Range is 0.25-4.0 for the REST API; the Agents Platform restricts to 0.7-1.2."*

**Status: DOC on both sides, contradictory.** Treat 0.7–1.2 as the safe range; anything
outside it is **UNVERIFIED** from this container.

### Baseline recommendation (DOC)

*"The most common setting is stability around 50, similarity around 75, and keeping style at
0, with minimal changes thereafter."*

### How they interact (DOC)

- Sliders are **ranges, not values**: *"the AI is non-deterministic; setting the sliders to
  specific values won't guarantee the same results every time. Instead, the sliders function
  more as a range, determining how wide the randomization can be between each generation."*
- Lower stability ⇒ more inter-generation variability ⇒ **more re-rolls needed**. Higher
  stability ⇒ *"you usually don't need to generate as many samples."* This is a direct
  cost lever, not only a taste lever.
- `style > 0` and `use_speaker_boost = true` both cost latency; `style > 0` also costs
  stability.
- Flash models *"ignore some voice settings for speed"* (ElevenLabs skills repo) — **DOC** in
  that source, not repeated in the main docs.

### v3 specifically — Creative / Natural / Robust

DOC (<https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices#settings>):

> *"The stability slider is the most important setting in v3, controlling how closely the
> generated voice adheres to the original reference audio."*
> - **Creative:** *"More emotional and expressive, but prone to hallucinations."*
> - **Natural:** *"Closest to the original voice recording—balanced and neutral."*
> - **Robust:** *"Highly stable, but less responsive to directional prompts but consistent,
>   similar to v2."*
> *"For maximum expressiveness with audio tags, use Creative or Natural settings. Robust
> reduces responsiveness to directional prompts."*

And: *"Speed is not available for the Eleven v3 model."*, *"Similarity is not available for
the Eleven v3 model."*, *"Speaker Boost is not available for the Eleven v3 model."*

**The numeric mapping Creative = 0.0, Natural = 0.5, Robust = 1.0 is NOT in the
documentation.** The v3 stability control is presented only as three named modes in the UI,
while the API exposes a continuous 0.0–1.0 double with no v3-specific note. The mapping is
widely repeated and is plausible, but it is **FOLK / UNVERIFIED** as of 2026-08-19 — do not
put it in code as if it were documented.

---

## 5. Request stitching

Sources: <https://elevenlabs.io/docs/eleven-api/guides/how-to/text-to-speech/request-stitching> ·
<https://elevenlabs.io/docs/api-reference/text-to-speech/convert>

| Parameter | Type | Limit | Behaviour (DOC) |
|---|---|---|---|
| `previous_text` | string, nullable | none published | *"The text that came before the text of the current request. Can be used to improve the speech's continuity when concatenating together multiple generations."* |
| `next_text` | string, nullable | none published | *"The text that comes after the text of the current request."* |
| `previous_request_ids` | list of string | **max 3** | *"A list of request_id of the samples that were generated before this generation… The results will be best when the same model is used across the generations."* |
| `next_request_ids` | list of string | **max 3** | *"especially useful for maintaining the speech's continuity when regenerating a sample that has had some audio quality issues."* |

Precedence (**DOC**): *"In case both `previous_text` and `previous_request_ids` is send,
`previous_text` will be ignored."* Same for `next_text` / `next_request_ids`.

Hard constraints (**DOC**, all from the stitching guide / API reference):

- **Not available for `eleven_v3`.** *"Request stitching is not available for the `eleven_v3` model."*
- Request IDs must be **no older than two hours**.
- The prior request must have **processed completely** — with streaming, *"the audio has to
  be read completely from the response body"* before its id is usable.
- Available on every plan *"unless you are an enterprise user with increased privacy requirements."*
- `enable_logging=false` (zero-retention mode) **disables request stitching** for that request.
- The `request-id` comes back in the **response headers**, so the raw response must be
  captured (`with_raw_response` in Python, `.withRawResponse()` in TS).
- *"How much difference does Request Stitching make? The difference depends on the model,
  voice and voice settings used."* — no quantified benefit is published.

Best practice for chunking long scripts (**DOC**,
<https://elevenlabs.io/docs/overview/capabilities/text-to-speech#key-facts>):
*"Split long text into segments; use the `previous_text` / `next_text` parameters to maintain
natural prosody across chunks."*

The docs give **no recommended chunk size**. The official example chunks by sentence/clause.
Any specific "400–600 characters is the sweet spot" figure is **FOLK** as far as ElevenLabs
documentation goes (this repo derived its own 450 — see Part 2 §2).

---

## 6. Seed, determinism, re-rolling

| Fact | Source | Status |
|---|---|---|
| `seed` is an integer, `0`–`4294967295`, nullable | API reference | **DOC** |
| *"our system will make a **best effort** to sample deterministically, such that repeated requests with the same seed and parameters should return the same result. **Determinism is not guaranteed.**"* | API reference | **DOC** |
| *"Output is nondeterministic — use the `seed` parameter for more consistent results"* | TTS capabilities, Key facts | **DOC** |
| *"The models are nondeterministic. For consistency, use the optional seed parameter, though subtle differences may still occur."* | TTS capabilities FAQ | **DOC** |
| Free regenerations: **2 per generation**, website only, same prompt + voice + model, first generation < 2 hours ago, page not refreshed. Voice-setting sliders **may** be changed and it still counts as free. | <https://elevenlabs.io/docs/help-center/account/general/do-i-use-quota-on-every-generation> | **DOC** |
| *"Free regenerations for Text to Speech and Speech to Speech are only available via the website. They are **not** available via the API."* | same | **DOC** |
| v3 differs: *"Each time you click Generate, you'll get two alternative outputs, but you're only charged for one."* (website) | same | **DOC** |
| *"regenerations will solve roughly half of issues with quality, with remaining issues usually due to poor training data"* — ElevenLabs' internal benchmark | TTS capabilities FAQ | **DOC** |
| Changing `seed` as a deliberate re-roll strategy | — | **FOLK** (sensible, but not a documented workflow) |

**Practical reading:** re-rolling via the API always costs credits. The only free re-roll
mechanism is the website. So an API pipeline's cheapest correction is *not* re-generating.

---

## 7. Cost / credit implications

Sources: <https://elevenlabs.io/docs/help-center/account/general/what-are-credits> ·
<https://elevenlabs.io/docs/help-center/technical/what-models-do-you-offer-and-what-is-the-difference-between-them> ·
<https://elevenlabs.io/docs/overview/models>

- *"Credits were previously referred to as 'characters.'"* **DOC**
- **1 character = 1 credit for UI generations**, for `eleven_v3`, `eleven_multilingual_v2`,
  `eleven_flash_v2_5` and `eleven_flash_v2` alike, *"excluding credit multipliers"*. **DOC**
- *"API generations are discounted"* — the actual rates live on the pricing page, not the
  docs. **DOC that a discount exists; the rate itself is UNVERIFIED here.**
- Flash: *"50% lower price per character for API generations."* **DOC**
- Credits roll over up to two months' worth. **DOC**

Per-lever cost consequences:

| Lever | Billed? | Note |
|---|---|---|
| Audio tags `[sighs]` | **Yes** — they are characters in `text` | No exemption is documented. A 40-tag pass at ~9 chars/tag ≈ +360 credits on a 12k script. |
| `<break time="1.5s" />` | **Yes** — 24 characters each | Same reasoning. |
| Pronunciation respellings | **Yes**, and respellings are usually *longer* than the word | This repo already records that: `explaintory-voiceover/SKILL.md` — *"Respellings are longer than the words they replace, and that is billed."* |
| `previous_text` / `next_text` | **UNVERIFIED** | The docs never state whether conditioning text is billed. The API bills on `text`; conditioning is a separate field. **Do not assume it is free — measure it against the response header before building a budget on it.** |
| `previous_request_ids` / `next_request_ids` | Free (ids, not text) | No text is sent. |
| Higher `style`, `use_speaker_boost` | Free in credits, costs latency | **DOC** |
| Lower `stability` | Free per call, but **DOC** says you need more generations to land a good one — so it raises expected total spend |
| Re-rolls via API | Full price every time | Free regeneration is website-only. **DOC** |

Cost observability: the stitching guide names the header **`character-cost`**
(*"response headers also contains useful information like 'character-cost', which shows the
cost of the generation in characters"*), while ElevenLabs' own published skill names
**`x-character-count`**. **Both are official; they disagree. Read whichever the SDK actually
returns rather than trusting either name — UNVERIFIED.**

---

## 8. Known failure modes for long-form narration, and the documented mitigations

| Failure mode | Documented mitigation | Source |
|---|---|---|
| Abrupt prosody change at chunk boundaries | Request stitching (`previous_text`/`next_text`, `previous_request_ids`) | stitching guide |
| One bad chunk in the middle of a good sequence | `next_request_ids` — regenerate clip 2 with clip 1's id as previous and clip 3's id as next | API reference |
| Exceeding the per-request character limit | Split; limits are per model (5k / 10k / 30k / 40k) | models page |
| Break-tag overuse → speed-up, noise, artifacts | Use fewer break tags; *"Use `<break>` tags consistently"* | best practices |
| Voice inserts "uh"/"ah" in pauses | Voice-dependent; choose a different voice | help centre |
| Numbers, dates, currency, phone numbers misread | Use `eleven_multilingual_v2`; or `apply_text_normalization: "on"`; or pre-normalize the text (docs give a full LLM prompt and Python/TS regex examples) | best practices → Text normalization |
| Flash v2.5 reading "$1,000,000" as "one thousand thousand dollars" | Same — normalization is **off by default on Flash v2.5** for latency; Enterprise-only to enable | models page → Considerations |
| Emotional/descriptive guidance being spoken aloud | Remove it in post-production; **or** use v3 audio tags instead | best practices, TTS capabilities |
| v3 hallucinations at Creative stability | Use Natural or Robust | best practices → Settings |
| PVC voices under-performing on v3 | Use an IVC or designed voice during the research-preview stage | best practices → Voice selection |
| Voice sounds unnaturally fast / paced badly | *"The pacing of the audio is highly influenced by the audio used to create the voice… we recommend using longer, continuous samples"*; plus the `speed` setting | best practices → Pace |
| Monotone cloned voice | *"the speaking style in the samples you upload for cloning is replicated… If the speech in the uploaded sample is monotone, the model will struggle to produce expressive output."* | help centre → How to produce emotions |
| Inconsistent output run to run | `seed` (best-effort only); raise `stability` | API reference, playground docs |
| Mispronunciation | v3 inline IPA (80–90%); `eleven_flash_v2` phoneme tags; **alias tags / respelling for every other model** | best practices → Pronunciation |
| Very long content generally | *"we highly recommend using Studio"* for content over a few thousand characters | help centre → max characters |

Not documented anywhere, and therefore your own problem:
**clicks at butt-joined chunk boundaries**, **stranded phoneme fragments in inserted gaps**,
**true-silence vs aligner-gap discrepancy**, **loudness targets**. Every one of those is
solved in this repo by post-processing (Part 2 §4).

---

# PART 2 — What this repo's pipeline already does

## 0. There are two separate pipelines, and only one of them is the ElevenLabs one

| | **A. Production ElevenLabs pipeline** | **B. `vo-studio` desktop app** |
|---|---|---|
| Root | `/home/user/Test-2/.claude/skills/explaintory-voiceover/scripts/` | `/home/user/Test-2/vo-studio/vostudio/` |
| Driver | `voiceover.py` (`main()`), documented by `.claude/skills/explaintory-voiceover/SKILL.md` | `pipeline.py:run()` |
| Default engine | ElevenLabs, always | **Chatterbox on local GPU** (`config.py:Generation.engine = "chatterbox"`); ElevenLabs is an optional second engine |
| Mastering | `explaintory-vo-master/scripts/humanize.py` | its own `master.py:master()` |
| Read-check | `readcheck.py` + `faster-whisper distil-large-v3` | `readcheck.py` + `faster-whisper distil-large-v3` |

The task named `vo-studio/vostudio/*`. Those files are documented below, but **the pipeline
that actually sends ElevenLabs requests for the channel is A**, and everything about
`previous_text`, `next_text` and request stitching lives there. Both are covered.

**One missing file, flagged:** `/home/user/Test-2/.claude/skills/explaintory-vo-master/SKILL.md`
**does not exist**. That directory contains only `scripts/humanize.py`. The skill text lives
outside the repo at `/root/.claude/skills/synced/explaintory-vo-master/SKILL.md` (128 lines,
container-synced). It is therefore **not version-controlled in this repo** and dies with the
container — the same failure mode `HANDOFF.md` and `voice-calibration.json` exist to prevent.

---

## 1. Exact current voice settings and model

### Pipeline A — the locked-in calibration

`/home/user/Test-2/voice-calibration.json` → `calibration`:

| Key | Value |
|---|---|
| `voice` | `dUHbvtIZto0ZEBkhYiyk` |
| `model` | **`eleven_multilingual_v2`** |
| `stability` | **0.48** |
| `similarity_boost` | **0.80** |
| `style` | **0.05** |
| `speed` | **1.07** |
| `use_speaker_boost` | **true** |
| `collapseBreaks` | false |
| `chapterPause` | `natural` |
| `skipHeadings` | false |
| `pronOn` | **false** (deliberate — Sapro chose the raw take over the respelled one) |
| `chunkSize` | **450** |

These are loaded by `scripts/generate.py:load_profile()`, which also builds a `source` map
recording whether each value came from `env`, `profile`, `default` or `unset`. That map is
printed by `scripts/voiceover.py:plan()` (line ~263) under `CALIBRATION`, with a
`^ N value(s) nobody chose` line for anything marked `(default)`.

The code defaults, used only when the profile omits a key —
`scripts/generate.py:DEFAULT_SETTINGS` / `DEFAULT_MODEL`:

```
stability 0.50 · similarity_boost 0.75 · style 0.0 · use_speaker_boost True · speed 1.0
model eleven_multilingual_v2
```

`similarity_boost` 0.75-vs-0.80 is the exact drift the provenance printer was built for; the
skill calls it out explicitly.

Output format is fixed at `scripts/generate.py:OUTPUT_FORMAT = "mp3_44100_128"`, decoded to
48 kHz mono PCM at stitch time (`generate.py:_decode()`, `SR = 48000`).

### Pipeline B — `vo-studio`

- `vo-studio/vostudio/config.py:Eleven` → `model = "eleven_multilingual_v2"`,
  `stability = 0.55`, `similarity_boost = 0.85`, `style = 0.10`, `speaker_boost = True`,
  `voice_id = ""`, `api_key = ""`.
  The docstring is explicit that these are **not** the channel's measured numbers:
  *"They are a STARTING POINT, not measured on this channel the way the Chatterbox numbers were."*
- **`speed` is not sent to ElevenLabs at all** in pipeline B.
  `vo-studio/vostudio/eleven.py:synthesize()` builds `voice_settings` with only
  `stability`, `similarity_boost`, `style`, `use_speaker_boost`. Speed is applied afterwards
  with ffmpeg `atempo` in `vo-studio/vostudio/generate.py:Generator.generate_chunk()` →
  `voice_profile.py:apply_speed()`.
- `vo-studio/vostudio/eleven.py:USD_PER_1K_CHARS = 0.18`, used by `estimate_usd()` and logged
  per chunk in `generate.py:Generator.generate_chunk()`.
- `vo-studio/vostudio/eleven.py` module docstring: *"None of it has run against the live
  service from this machine — there is no key here."* **So pipeline B's ElevenLabs path is
  unproven code.**

---

## 2. How the script is chunked, and whether `previous_text` / `next_text` are used

### Pipeline A — yes, fully

`scripts/script_prep.py`:

- `MAX_CHUNK = 450` — *"chars per TTS request. 400-600 is the studio's sweet spot: the voice
  model drifts over a long generation and holds its best delivery for ~30s."*
  (This is the repo's own finding; ElevenLabs publishes no such figure — see Part 1 §5.)
- `CONTEXT_CHARS = 300` — the conditioning window.
- `split_script(text, max_chunk)` — paragraph boundaries first; a too-large paragraph is split
  on sentences (`[^.!?…]+[.!?…]+["'"']*\s*`); units are then greedily merged back up to
  `max_chunk`; **never splits mid-sentence** except when a single sentence exceeds the limit,
  in which case it cuts at the last space (`s.rfind(" ", 0, max_chunk)`).
- `build_sections()` produces `{index, text, send_text, is_heading, is_cta, chars}`.
  `text` keeps the control markers (`\x01` section break, `\x02` pause marker);
  **`send_text` is what goes to the API.** This split is the key extension point (§6).
- `detect_structure()` / `narration_text()` classify headings, CTAs and dividers;
  `split_pronunciation_guide()` strips the script's trailing pronunciation glossary so the
  video does not recite it; `split_read_note()` strips animator notes.

`scripts/generate.py:tts(client, prof, sections, index, prev_ids)` — the request builder:

```
kw = dict(voice_id, text=sec["send_text"], model_id, output_format, voice_settings=VoiceSettings(**prof["settings"]))
if prev and not fresh_start:  kw["previous_text"] = prev["send_text"][-CONTEXT_CHARS:]     # last 300 chars
if nxt:                       kw["next_text"]     = nxt["send_text"][:CONTEXT_CHARS]       # first 300 chars
if not fresh_start and prev_ids: kw["previous_request_ids"] = prev_ids[-3:]                # ElevenLabs max
```

- `fresh_start = bool(prev and prev["is_heading"])` — **conditioning is deliberately dropped
  immediately after a chapter announcement**, so the narration does not continue the
  heading's sentence.
- `next_request_ids` is **not used anywhere in the repo.** That is the parameter ElevenLabs
  documents for regenerating a middle clip (Part 1 §5) — and `regen_span.py` /
  `voiceover.py`'s redo loop are exactly that case. **Gap.**
- Request ids are captured via `client.text_to_speech.with_raw_response.convert(**kw)` and
  `headers.get("request-id") or headers.get("x-request-id")`, persisted to
  `<parts_dir>/request_ids.json` by `generate.py:generate_sections()`.
- Retries: 4 attempts, exponential backoff from 2 s, on 429/500/502/503/504; 401 and 402 fail
  immediately with a specific message.

### Pipeline B — no

`vo-studio/vostudio/script_prep.py:chunk_text()` / `parse_script()` chunk at
`max_chars_per_chunk = 300` (`config.py:Generation`) on sentence boundaries, splitting a long
sentence at commas and only then at spaces. `vo-studio/vostudio/eleven.py:synthesize()` sends
**`text`, `model_id`, `voice_settings` and nothing else** — no `previous_text`, no
`next_text`, no `previous_request_ids`, no `seed`. Every chunk is generated cold.

**`seed` is never sent to ElevenLabs by either pipeline.** `vo-studio/vostudio/config.py:Generation.seed`
exists but is consumed only by `vo-studio/vostudio/generate.py:Generator._seed()`, which seeds
`torch`/`random`/`numpy` for **Chatterbox**.

---

## 3. Every place pause / timing is manipulated

Ordered by when it happens.

### Pipeline A

| # | Where | What |
|---|---|---|
| 1 | `script_prep.py:PAUSE_PRESETS` | Inserted digital silence, in seconds: `tight {before .10, after .18, cta .20}`, **`natural {before .22, after .30, cta .30}`**, `wide {before .40, after .55, cta .55}`. The comment records the *measured finished* result of `natural`: ~0.33–0.41 s before a chapter name, ~0.39–0.57 s after. |
| 2 | `script_prep.py:chapter_gaps(sections, preset)` | `gaps[i]` = silence inserted **before** section `i`. `max()` of: `before` if the section is a heading, `after` if the previous section was a heading, `cta` if it is a CTA. **Forced to 0.0 for `i == 0`** — no dead air at the top of the video. |
| 3 | `generate.py:stitch()` | Writes `b"\x00\x00" * int(round(gaps[i] * rate))` — **exact digital silence**, then the section, and records `marks` (start/end/retimed) so a flagged section maps to a timestamp. |
| 4 | `generate.py:SPLICE_FADE = 0.003` / `_edge_fade()` | 3 ms linear ramp on the first and last samples of every section. Prevention, not detection: the comment records that a sample-step click detector *"tuned to catch all three he reported also flagged several hundred ordinary plosives."* |
| 5 | `generate.py:level_headings(parts_dir, sections, tol=0.12, floor=0.85, ceil=1.18)` | Measures every chapter announcement in **syllables per second over the spoken span only** (`_speech_rate()`, `_syllables()`, `_digit_syllables()`), takes the median of the *other* headings as target, and applies an `atempo` factor to any heading more than 12% away, clamped to ×0.85–×1.18. Needs **3+ headings**. Exists because the first heading has no `previous_text` and no `previous_request_ids` and therefore rushes — *"the cause is structural, so re-rolling it does not reliably help."* Disabled with `--no-level-headings`, which the SKILL.md says the last delivery actually used. |
| 6 | `readcheck.py` (via `voiceover.py`) | Flags **dead air ≥ 0.7 s inside a section** and speaking rate outside **120–240 wpm**. Edge silence is explicitly not counted. An off-rate section is only re-rendered if the transcript *also* mismatches. |
| 7 | `humanize.py:DEFAULTS` | `comma=0.16, sentence=0.21, paragraph=0.25, tail=1.00, tempo=1.04, air=0.00` seconds. Section/era cards: *"leave alone (already ~0.45 s)"*. Within a sentence: *"never touch"*. |
| 8 | `humanize.py:RUNTHROUGH = 0.060` | *"Silence below this at a comma means the voice deliberately read through it."* Raised from 0.030 because 30–50 ms beats were articulatory closure, not intended pauses. **Applies to commas/clause breaks only** — sentence and paragraph boundaries are deliberately excluded, because a run-together sentence pair is a generation artefact the master should repair. |
| 9 | `humanize.py:build()` | Inserts the pause by **true silence measured per boundary in the last 0.35 s before the next word onset**, cutting at the minimum-energy frame within 0.30 s before that onset (never mid-gap — a mid-gap cut once landed inside "K22"/"K14"), with 4 ms fades. |
| 10 | `humanize.py` boundary detection | Three rules: script punctuation read from the **script text** not the aligned token list (pure-digit tokens fall out of alignment and take their punctuation with them); **post-date** beats (`_is_range()` suppresses the beat inside "between 1547 and 1550"); and the **curated `wordA\|wordB` clause-break file**. |
| 11 | `humanize.py` `--max-wpm` | Per-sentence levelling, default **0 = off**. Skips the first 25 s (`--level-skip-start`), never stretches past 13% (`--min-factor 0.87`). SKILL.md records that 290 touches nothing and 250 flattens the channel's real punchlines (measured human: 290 and 283 wpm). |
| 12 | `humanize.py` `--tempo 1.04` | Global +4% `atempo`, applied before pause insertion (`raw_filter(dc, sp, SR, f"atempo={a.tempo}")`). `--adaptive-tempo` is on by default. |
| 13 | `humanize.py:fix_glitches()` | Removes splice fragments **only** when both isolated by silence **and** within 50 ms of a hard digital splice edge. `--keep-glitches` disables. |
| 14 | `scripts/orphans.py` | Post-delivery sweep for short bursts fenced by silence on both sides; decides each by muting and re-transcribing — **KEEP if words are lost, ORPHAN if nothing is**. Never edits the file. |

**No `<break time="…" />` tag is emitted anywhere in this repo.** `grep -rn "break time\|<break\|ssml"` across
`.claude/skills/explaintory-voiceover/scripts/` returns nothing. All pause control is
post-generation silence insertion.

**`collapseBreaks` is inert.** It is present in `voice-calibration.json`, read by
`generate.py:load_profile()` into `prof["collapse_breaks"]`, and printed in the plan by
`voiceover.py:plan()` (line 360) — but it is never read by any code that transforms text.
It is a value the approval gate presents as "about to be committed" that does nothing.

### Pipeline B

| Where | What |
|---|---|
| `vo-studio/vostudio/config.py:Master` | `comma_pad_ms = 160.0`, `runthrough_threshold_s = 0.060`, `chapter_gap_s = 0.30`, `edge_fade_ms = 3.0` |
| `vo-studio/vostudio/master.py:find_gaps()` | Gaps measured from a 10 ms RMS envelope at `floor_db = -45.0`, `min_dur = 0.020`. Explicitly **not** from ASR word timestamps: *"faster-whisper returns contiguous spans… so a real 150 ms hole reads as 0.000 s."* |
| `vo-studio/vostudio/master.py:comma_times()` | Locates scripted commas by greedy alignment of script words to ASR word end-times, expanding ASR numerals through `spell_numerals()` first so a year does not desynchronise the walk. |
| `vo-studio/vostudio/master.py:place_beats()` | Pads a gap to 160 ms **only** when a located comma lands on it and the gap is ≥ `runthrough_threshold_s` (0.060) and < target. If there are no word timings it does **nothing** — *"which is the safe direction to fail in."* Applied back-to-front so earlier edits do not shift later gap positions. |
| `vo-studio/vostudio/master.py:set_gap()` | Fades the audio each side of the seam (not the silence) before splicing in `np.zeros(target_s * sr)`. |
| `vo-studio/vostudio/generate.py:join()` | 3 ms fade-in/fade-out on every chunk edge before concatenation. |
| `vo-studio/vostudio/config.py:Generation.speed` + `voice_profile.py:apply_speed()` | Post-generation `atempo`, chained in ≤2.0×/≥0.5× steps. Measured: `atempo` moves median f0 0.2–1.5%, librosa's phase vocoder moves it 4.5–8.5%. |

---

## 4. What the mastering chain does to dynamics, EQ and level

### Pipeline A — `explaintory-vo-master/scripts/humanize.py`

Documented order (module docstring):
`decode → declip → forced alignment → boundary detection → pause insertion → studio master → loudnorm`.

| Stage | Function | Detail |
|---|---|---|
| Decode | `decode_raw()` | 48 kHz mono float32; a 16 kHz mono copy for alignment |
| **Declip** | `declip(x, thr=0.95, guard=8)` | Reconstructs over-full-scale runs by **cubic fit**, not limiting |
| QC | `qc_report()` | Reports full-scale sample counts; reports a sibilant peak s/mid ratio and warns *"de-esser will be working hard"* |
| Glitch repair | `fix_glitches()` | Zeroes splice fragments within 50 ms of a hard digital edge |
| Alignment | `align()` | torchaudio **MMS_FA**, chunked at 40 s. Aborts non-zero if implied wpm is outside **90–260** or mean confidence is under **0.55** |
| Pacing | `build()` | Per-boundary true-silence targeting (§3 rows 7–12) |
| **EQ** | `master()` → `EQ_CURVE` | A **56-point matched-EQ curve derived once by force-aligning the channel's real human VO stem**, applied as a 2047-tap `firwin2` FIR via `fftconvolve`. Notable moves: **+4.8 dB @ 101 Hz**, **−2.4 dB @ 570 Hz**, **+5 dB @ 3620 Hz**, **+6 dB @ 6451 / 11494 / 12902 Hz** |
| High-pass | `master()` | 3rd-order Butterworth HPF at **55 Hz** |
| Exciter | `master()`, `air` | `DEFAULTS["air"] = 0.00` — **off, approved 2026-07-29**. `classic` mode (tanh drive at 8×, 8.5–14 kHz and 13–19 kHz bands, envelope-gated) is the default; `local` (square-law, gated) exists and is *"technically cleaner… but a different top end and has not been signed off"* |
| **De-esser** | `master()` | Split-band 5.2–9.5 kHz, envelope follower at 1 ms attack / 40 ms release against a 5 ms/150 ms broadband reference, threshold ratio **`TH = 0.42`**, gain reduction `(TH/ratio)**0.55`, smoothed by a 120 Hz LPF and **clamped to ≥ 0.45** (max ~6.9 dB of reduction). Subtractive: `return y - sib*(1-gr)` |
| **Loudness** | ffmpeg | `loudnorm=I=-14:TP=-1.5:LRA=7:linear=true` at 48 kHz mono |

**There is no broadband compressor.** Dynamics are touched only by declipping (upward
reconstruction), the de-esser (band-limited downward), and `linear=true` loudnorm (pure gain).
The human reference is **LRA 1.6 LU**, and the skill's "do not repeat these mistakes" list
records that an audio model's claim that the AI was flatter than the human was wrong in the
other direction.

Human reference targets (SKILL.md, measured by force-alignment of the real stem):
overall **181 wpm**, articulation **197 wpm**, silence **7.8%**, **longest pause anywhere
0.43 s**, LRA **1.6 LU**, median sentence 200 wpm.

### Pipeline B — `vo-studio/vostudio/master.py`

Much simpler and deliberately so:

- `master()` = `place_beats()` → `normalize()` → write PCM_24.
- `normalize(audio, sr, cfg)` — **gain only, no limiting**: *"A limiter would reshape the read
  to buy level, and the read is the product."* Targets `config.py:Master.target_lufs = -14.0`
  and `target_true_peak = -1.5`. If the true peak would exceed the ceiling it pulls the whole
  file down and **reports that loudness lands under target** rather than compressing.
- `measure_loudness()` — pyloudnorm integrated LUFS; true peak by **4× polyphase resample**.
  The comment records that the previous `np.interp` "4× oversample" was mathematically
  identical to the sample peak and was **understating sibilance by over 3 dB**.
- **No EQ, no exciter, no de-esser at all.**
- Headroom is applied at birth instead: `vo-studio/vostudio/generate.py:apply_headroom()`
  scales every chunk to a **−3.0 dBFS** ceiling and *logs* (never repairs) samples that
  arrived at full scale. This is applied on the ElevenLabs branch too
  (`Generator.generate_chunk()` — the comment records that it used to be skipped there).
- Delivery: `vo-studio/vostudio/pipeline.py:run()` encodes to `libmp3lame -b:a 320k` mono at
  48 kHz.

---

## 5. Insertion points for a new style layer, by file and function

Read "V2 style layer" two ways; both are covered.

### 5a. If the layer only *rewrites the text sent to the API* (tags, breaks, punctuation, emphasis)

**The correct seam already exists and is already used once.** `script_prep.py:build_sections()`
produces two fields per section:

- `text` — keeps markers; feeds gap computation
- `send_text` — what the API receives

and `scripts/pronounce.py:apply_to_sections(sections, lex)` already mutates **only**
`send_text`, called from `scripts/generate.py:main()` right after `build_sections()`:

```
lex = pronounce.load_lexicon(a.lexicon)
if lex:
    pronounce.check_lexicon(lex, prof["model"])
    used = pronounce.apply_to_sections(sections, lex)
```

**Insertion point 1 — `generate.py:main()`, immediately after the `pronounce` block.**
A `style.apply_to_sections(sections, style_spec)` call there inherits every property that
makes the lexicon safe: the read-check still diffs ASR against the real script, and
`humanize.py` still aligns against the real script, so nothing downstream is fooled.
It must also re-count `sec["chars"]` after mutation, exactly as the lexicon path implicitly
does — `chars` is computed in `build_sections()` from `send_text` and is what the budget gate
counts.

**Insertion point 2 — `pronounce.py:check_lexicon(lex, model)` is the precedent for a model
capability guard.** It warns when a lexicon entry looks like IPA on a model that will ignore
it. A style layer needs the same guard, harder: **audio tags on `eleven_multilingual_v2` are
not audio tags, they are words** (Part 1 §2e). A `style.check_model(spec, prof["model"])` that
*refuses* rather than warns belongs here.

**Insertion point 3 — `script_prep.py:build_sections()` itself**, if the layer needs to change
where sections split (e.g. one request per emotional beat). Changing this changes `chars`,
therefore the budget, therefore the approval gate — so it is the more invasive option.

### 5b. If the layer changes *generation parameters* (per-section stability/style, model, seed)

**Insertion point 4 — `generate.py:tts(client, prof, sections, index, prev_ids)`.**
This is the only place a request is assembled. A per-section settings override goes into the
`kw = dict(...)` block, and `seed` / `next_request_ids` would be added here too. Note the
existing precedent: `voiceover.py`'s redo loop already varies stability per round by passing
`--stability` to a whole `generate.py` invocation (`voiceover.py`, redo block:
`nudged = min(1.0, prof["settings"]["stability"] + 0.05 * rnd)`), which is coarse — it is
per-run, not per-section.

**Insertion point 5 — `generate.py:load_profile()` and `DEFAULT_SETTINGS`.** Any new knob must
be registered here *with its `src[...]` provenance entry*, or the approval gate cannot show
it. This is not optional bookkeeping: the skill records that `similarity_boost` silently fell
back to 0.75 precisely because the plan printed only the settings the profile happened to name.

**Insertion point 6 — `voiceover.py:plan()` (line ~263).** The CALIBRATION block, the
`inherited = [...]` list (line ~364) and the COST block all enumerate keys by name. A new knob
that is not added here is invisible at the gate.

### 5c. If the layer changes *timing* rather than text

**Insertion point 7 — `script_prep.py:PAUSE_PRESETS` + `chapter_gaps()`.** The only exact,
repeatable pause mechanism in the system. A style layer that wants "a longer beat before a
reveal" should almost certainly do it here, not with `<break>` tags — this costs zero credits
and zero stability.

**Insertion point 8 — `generate.py:stitch()` / `level_headings()`.** Post-generation retiming.

**Insertion point 9 — `humanize.py:DEFAULTS` and the `--curated` clause-break file.**
Per-boundary pause targets. **Locked** — see §6.

### 5d. Where a style layer must NOT touch

- `humanize.py:master()` and `EQ_CURVE` — SKILL.md: *"Do not re-tune the mastering settings.
  They were derived by force-aligning the channel's real human stem and signed off by ear."*
- `humanize.py` `--exciter local` — exists, not signed off.
- `readcheck.py`'s comparison target — it must keep diffing against the **real** script text.
  Any tag that leaks from `send_text` into `text` inflates WER on every section that has one.

---

## 6. Hard constraints a new layer must respect

| Constraint | Where enforced | Detail |
|---|---|---|
| **Approval quote required for every send** | `generate.py:main()` | `--approval "<his actual words>"`. No text ⇒ `SystemExit` printing every section that would be sent, with its text and char count. SKILL.md records *why* it moved into code: the rule was written down, the agent restated it more permissively, and used its own restatement as authorisation. *"A rule an agent may restate is not a rule."* An earlier approval does not carry forward. |
| **Budget backstop** | `generate.py:main()` | `--budget` default **1000** characters. *"a backstop against a runaway send, NOT an allowance."* Lowered from 2000 on 2026-08-14. `--approve-spend N` raises the ceiling: `ceiling = max(a.budget, a.approve_spend)`. |
| **Run-wide spend ledger** | `generate.py:spend_so_far()` / `record_spend()` | `<work>/spend.json`, debited **per section immediately after it is sent**, not per invocation. An unreadable ledger returns `-1` and is treated as **exhausted**. This exists because redo rounds re-used the same command line and therefore received a fresh full-size budget each round — true worst case was `approve_spend × (1 + max_redos)`. |
| **Plan gate before generation** | `voiceover.py:plan()` + `--plan` | Prints chapter list, section/char counts, the full CALIBRATION block with provenance, PRE-FLIGHT pronunciation-guide cross-check, first-pass cost, **and worst-case cost across redo rounds**. Generation is the one irreversible step. |
| **`--max-redos` defaults to 0** | `voiceover.py` | `max_redos = a.max_redos if a.max_redos is not None else (2 if auto_redo else 0)`; `redo_rounds = max_redos if auto_redo else 0`. **Nothing is re-rendered without `--auto-redo`.** With neither, the check stage prints the flagged sections, the ASR evidence, the character cost, and hands over the command that would do it. |
| **Redo escalation is fixed** | `voiceover.py` redo loop | Round 1 = plain re-roll. Rounds ≥ 2 add `--stability` at `+0.05 × rnd`. A word that comes out identically on two takes stops being re-rendered (`readcheck.settle_repeats()`) and is reported as *"consistent across takes, worth a listen"*. |
| **Repair granularity** | SKILL.md + `regen_span.py` | *"Never re-roll a section to fix a word."* Use `regen_span.py` on the sentence (134 chars vs 403), spliced inside measured silence; it refuses when there is no silence at an edge and auto-reverts if a word goes missing. |
| **Check the raw take first** | SKILL.md | Measure the defect in the RAW section file. Clean there ⇒ the stitch or the master caused it ⇒ fix there, **zero credits**. A re-render is the last option, not the first. |
| **Prove a destructive edit did not eat a word** | SKILL.md, `orphans.py`, `pipeline.py:run()` (B) | Any edit that silences or removes audio must be re-transcribed and diffed against the script before it is reported or sent. Test for words **LOST**, one-sided — never for words *different*, because muting a corrupting fragment can make ASR *recover* a word. |
| **Confirm on the excerpt, not the file** | SKILL.md | Send six seconds around the fix, cut from the stitch; master only after confirmation. |
| **Never treat a listening model's description as data** | both SKILLs | vo-master's list of eight wrong "measurements" from an audio model is the evidence. |
| **Full logs to file, filter at read time** | SKILL.md | *"a filter on the pipe decides, before the output exists, what will ever be knowable"* — it lost a master's repair counts once. |
| **Every stage exits non-zero if it produced no artifact** | `voiceover.py:assert_artifact()`, `generate.py:main()` | The stitch's duration is checked against the section marks (`got < expect * 0.9` ⇒ abort). Exit code 1 is an **abort**, not a warning. |
| **`pronOn` is false on purpose** | `voice-calibration.json` | Sapro compared raw against respelled and chose raw. The guide is a checking reference, not an automatic substitution. |
| **Mastering settings are locked** | vo-master SKILL.md | *"Defaults are the approved sound — do not change them without the user listening."* |

### The model-swap constraint, stated plainly

If a style layer wants **audio tags**, it needs `eleven_v3`. Moving to `eleven_v3` removes,
in one step:

1. **`previous_request_ids` / request stitching** — *"Request stitching is not available for
   the `eleven_v3` model."* That deletes the mechanism in `generate.py:tts()`, deletes the
   meaning of `fresh_start`, and **invalidates the documented cause of the "first chapter
   announcement reads fast" defect** that `generate.py:level_headings()` exists to repair.
   The repair would still run; its stated justification would no longer hold.
2. **`speed`** — `voice-calibration.json`'s `speed: 1.07`, tuned by ear over seven rounds,
   would be silently dropped by the API.
3. **`similarity_boost` 0.80** and **`use_speaker_boost` true** — both unavailable on v3.
4. **`<break>` tags** — already unused here, so no loss.
5. Character limit drops 10,000 → 5,000 per request. `chunkSize` is 450, so this does not bind.
6. **Stability semantics change** from a continuous slider to Creative/Natural/Robust, and
   the current 0.48 has no documented equivalent. The `+0.05 × rnd` stability nudge in
   `voiceover.py`'s redo loop would be operating on an undocumented scale.

A v3 layer is therefore not an increment on the current pipeline — it is a different
generation contract, and the conditioning/retiming machinery would need re-deriving from
scratch against measurement.

---

## 7. Explicit gaps and things not verified

| Item | Status |
|---|---|
| `/home/user/Test-2/.claude/skills/explaintory-vo-master/SKILL.md` | **Does not exist.** Only `scripts/humanize.py` is in the repo. SKILL.md was read from `/root/.claude/skills/synced/explaintory-vo-master/SKILL.md` — outside version control, dies with the container. |
| Whether `previous_text` / `next_text` are billed | **UNVERIFIED.** Not documented; not measurable here (no key). Material: at 300 chars each way × ~41 sections, this is up to ~24,600 conditioning characters against a 12,174-char script. |
| The `character-cost` vs `x-character-count` response header | **Contradictory in two official sources.** Neither pipeline reads either header. |
| v3 stability numeric mapping (0.0 / 0.5 / 1.0) | **FOLK / UNVERIFIED.** Only the three names are documented. |
| `eleven_v3` Conversational model id | **UNVERIFIED.** Named in the docs; its `model_id` is not published in the models table. |
| `speed` maximum (1.2 vs 4.0) | **Contradictory across official sources.** |
| Maximum number of `<break>` tags per generation | **Not published.** Only "too many causes instability". |
| Pipeline B's ElevenLabs path | **Never executed against the live service** — `vo-studio/vostudio/eleven.py` docstring says so. |
| `USD_PER_1K_CHARS = 0.18` in `vo-studio/vostudio/eleven.py` | Self-labelled *"Published rate, and it moves"*. **Not re-verified against the current pricing page** (the pricing page is outside the docs site and was not fetched). |
| `vo-studio/vostudio/generate.py:generate_chunk()` line 204 | **Live bug:** the local-Chatterbox speed branch references `spd`, which is only assigned inside the ElevenLabs branch (line 165). Any Chatterbox render with `speed is not None and abs(speed-1.0) >= 0.005` raises `NameError`. |
| No live audio was generated or measured in this session | All timing/quality figures are from the docs or from this repo's own recorded measurements. |
