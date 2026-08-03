"""The i2v prompt checker, tested against the documents it enforces.

Two tables carry this file. `WORKED_EXAMPLES` is every prompt `data/image-to-video.md` and
`data/i2v-prompt-cookbook.md` present as correct, and they must come back with nothing said
about them — a checker that flags the documents' own best work is a checker whose warnings
get ignored, and then the forbidden verbs go through too. `ANTI_PATTERNS` is all six
diagnoses from the cookbook plus the inline cases, and each must be caught by the specific
code that names it, because "something is wrong with this prompt" is not a diagnosis
anybody can act on.
"""

from __future__ import annotations

import pytest

from forgecast.skills import prompt_check

# --------------------------------------------------------------- the good examples

# Verbatim from the two documents. Kept verbatim on purpose: paraphrasing them into
# something the checker happens to like is how this test stops meaning anything.
WORKED_EXAMPLES: dict[str, str] = {
    "skeleton": (
        "A 70-year-old grandmother in a beige cardigan and reading glasses sits at a "
        "kitchen table reading a letter from the Social Security Administration, her face "
        "slowly shifting from confusion to alarm; static medium close-up at eye level; "
        "warm golden-hour light from frame-right, soft fill, slight shadow under eyes; "
        "mood is intimate concern with hint of dread; 16:9, 5 seconds, minimal camera "
        "motion, no cuts."
    ),
    "establishing_exterior": (
        "A small one-story brick house on a quiet residential street in suburban "
        "Cincinnati, late autumn, fallen leaves drifting across the front lawn in a slow "
        "breeze, an American flag on the porch swaying gently; slow push-in over 5 "
        "seconds; warm late-afternoon golden hour from frame-right, long shadows; mood is "
        "quiet domestic vulnerability; 16:9, 5 seconds, moderate camera motion, no cuts."
    ),
    "hook_close_up": (
        "A 47-year-old woman in a soft cream sweater in a study with bookshelves blurred "
        "behind; slowly closes a manila folder, pauses, looks just past the camera; static "
        "medium close-up at eye level; weighted soft warm key from camera-left, deep "
        "shadow on the right side of the face; mood is reluctant witness gravity; 16:9, 6 "
        "seconds, minimal camera motion, no cuts."
    ),
    "mechanism_diagram": (
        "A photoreal close-up of an old wooden file cabinet drawer slowly sliding open, "
        "revealing rows of beige folders with handwritten date tabs, a single hand pulling "
        "out one labelled \"1997\" and laying it flat; slow push-in following the folder, "
        "settling on the open file; warm desk-lamp key, deep shadow in the cabinet; mood "
        "is methodical, inevitable; 16:9, 6 seconds, smooth camera motion, no cuts."
    ),
    # The document's own illustration that background motion is free.
    "background_motion_is_free": (
        "A man reads a letter while leaves drift past the window; static medium close-up; "
        "warm window light from frame-left; mood is quiet dread; 16:9, 5 seconds, minimal "
        "camera motion."
    ),
    # "'reaches for and grabs' doubles the verb" — so the single form must pass.
    "one_action_only": (
        "A night-shift commuter picks up the phone; static medium shot; low-key single key "
        "light from frame-right; mood is urgent; 16:9, 4 seconds, no cuts."
    ),
}


@pytest.mark.parametrize("name", sorted(WORKED_EXAMPLES))
def test_a_worked_example_from_the_documents_passes_silently(name):
    result = prompt_check.review(WORKED_EXAMPLES[name])
    assert result.findings == (), result.summary()
    assert result.blocked is False
    assert result.summary() == "no issues found against the i2v prompt cookbook"


# --------------------------------------------------------------- the anti-patterns

# The six numbered diagnoses, in the cookbook's order, plus the inline cases the prose
# names. `code` is the finding that must be present; other findings may also fire — a
# fragment of a prompt is legitimately generic as well as chained.
ANTI_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    ("multi_action", "multi_action",
     "Walks to the door, opens it, steps outside, and waves.", ""),
    ("conflicting_conditions", "condition_conflict",
     "Overcast January afternoon with shafts of bright sunlight.", ""),
    ("frame_filling_text", "onscreen_text",
     "A letter on a kitchen table with the words 'YOUR BENEFITS HAVE BEEN REDIRECTED' "
     "clearly visible.", ""),
    ("generic_everything", "generic",
     "A man at a desk doing finance stuff in an office.", ""),
    ("camera_move_on_a_face", "face_camera_move",
     "Static close-up of a woman at her desk; the camera does a slow orbit around her.",
     ""),
    ("stylized_prompt_to_a_photoreal_model", "register_mismatch",
     "An anime-styled illustration of a woman on a rooftop at dusk; static medium "
     "close-up; soft neon key light from frame-left; mood is wistful defiance; 16:9, 5 "
     "seconds, no cuts.", "fal-ai/veo3/image-to-video"),
    # Inline in the cookbook: three actions where one belongs.
    ("chained_actions", "multi_action",
     "A detective reaches for the phone, picks it up, dials; static medium shot; low-key "
     "key light; mood is tense; 16:9, 5 seconds.", ""),
    ("doubled_verb", "multi_action",
     "A woman reaches for and grabs the folder; static medium close-up; warm key light; "
     "mood is urgent; 16:9, 5 seconds.", ""),
    ("chained_with_then", "multi_action",
     "A man opens the door, then steps outside; static wide shot; natural daylight; mood "
     "is calm; 16:9, 5 seconds.", ""),
)


@pytest.mark.parametrize(("code", "prompt", "model"),
                         [(code, prompt, model) for _, code, prompt, model
                          in ANTI_PATTERNS],
                         ids=[name for name, _, _, _ in ANTI_PATTERNS])
def test_every_anti_pattern_in_the_cookbook_is_caught(code, prompt, model):
    result = prompt_check.review(prompt, model=model)
    assert code in result.codes, result.summary()

    # A finding is a diagnosis, not a verdict: it has to say what to do instead, or the
    # caller has nothing to change and reruns the same prompt.
    finding = next(item for item in result.findings if item.code == code)
    assert len(finding.message) > 60
    assert finding.evidence, "a finding with no evidence cannot be checked"


# --------------------------------------------------------------------- the verb bank


@pytest.mark.parametrize(("verb", "prompt"), [
    ("fights", "Two men fight in an alley at night"),
    ("kisses", "A couple kisses under a streetlight"),
    ("hugs", "A father hugs his daughter at the door"),
    ("jumps", "A boy jumps over a fence"),
    ("climbs", "A hiker climbs a rock face"),
    ("swims", "A woman swims across a lake"),
    ("shaves", "A barber shaves a customer"),
    ("speaks", "A senator speaks to the camera"),
    ("talks", "A doctor talks about the results"),
    ("disappears", "The figure disappears into the fog"),
    ("transforms", "The building transforms into a tower"),
    ("multiplies", "The crowd multiplies across the square"),
    ("plays sports", "Two teenagers play basketball on a court"),
    ("performs surgery", "A surgeon performs surgery under theatre lights"),
    ("operates machinery", "A worker operates a machine on the factory floor"),
    ("writes paragraphs", "A clerk writes a paragraph in a ledger"),
    ("cuts hair", "A stylist cuts her hair in a salon"),
])
def test_a_forbidden_verb_blocks_the_submission(verb, prompt):
    """Forbidden means the charge is wasted, so this is a block rather than a note."""
    result = prompt_check.review(prompt)
    assert "forbidden_verb" in result.codes, prompt
    assert result.blocked is True
    assert verb in result.summary()


@pytest.mark.parametrize("prompt", [
    "A single figure runs down an empty corridor away from camera",
    "A hand throws a single stone into the water",
    "A car drives along a coast road",
    "A cup falls from the table edge",
    "A woman smiles slightly at the letter",
    "A dancer dances slowly in an empty studio",
])
def test_a_risky_verb_warns_without_blocking(prompt):
    """The document permits these under conditions no regex can check.

    Blocking them would refuse work the skill explicitly allows, and a checker that
    refuses legitimate prompts gets bypassed — taking the forbidden tier with it.
    """
    result = prompt_check.review(prompt)
    assert "risky_verb" in result.codes, prompt
    assert result.blocked is False
    assert "forbidden_verb" not in result.codes


def test_falls_is_risky_where_jumps_is_forbidden():
    """The distinction the document draws, in one test.

    "gravity plus body is fine, push-off plus gravity plus body is not" — so the two must
    not collapse into one tier.
    """
    assert "risky_verb" in prompt_check.review("A ladder falls against the wall").codes
    assert "forbidden_verb" in prompt_check.review("A man jumps off the wall").codes


def test_a_word_that_merely_contains_a_verb_is_not_that_verb():
    """"fallen leaves" is not the verb "falls".

    It comes straight out of the establishing-shot example, so a stem match here would
    warn on the document's own template every time it is used.
    """
    for prompt in ("fallen leaves drifting across a lawn",
                   "a talking-head shot of the host",
                   "handwritten date tabs on beige folders"):
        assert prompt_check.review(prompt).codes in ((), ("generic",)), prompt


# ------------------------------------------------------------------ the one-verb rule


def test_micro_expressions_and_postures_do_not_count_as_a_second_action():
    """The cookbook's hook template asks for an action *and* a micro-expression.

    Counting the micro-expression as a competing verb would flag the shape the document
    prescribes, which is the fastest way to make the rule useless.
    """
    result = prompt_check.review(
        "A woman sits at a table and slowly closes a folder, pauses, looks up; static "
        "medium close-up; warm key light; mood is weighted; 16:9, 5 seconds.")
    assert "multi_action" not in result.codes


def test_a_camera_move_is_not_an_action():
    """"the camera pushes in" is not the subject doing something.

    Counted as an action it would flag every prompt that described its camera, which is
    every prompt that follows the skeleton.
    """
    result = prompt_check.review(
        "A woman reads a letter; the camera pushes in slowly over 5 seconds; warm window "
        "light; mood is intimate; 16:9, 5 seconds.")
    assert "multi_action" not in result.codes


def test_the_multi_action_finding_names_the_verbs_and_the_number_of_clips():
    result = prompt_check.review("Walks to the door, opens it, steps outside, and waves.")
    finding = next(item for item in result.findings if item.code == "multi_action")
    for verb in ("walks", "opens", "steps", "waves"):
        assert verb in finding.message
    assert "4 clips" in finding.message


# ----------------------------------------------------------- conditions and camera


def test_a_conflicting_condition_names_both_halves():
    result = prompt_check.review(
        "An overcast January afternoon on a terraced street with shafts of bright "
        "sunlight; slow truck-right; mood is bleak; 16:9, 5 seconds.")
    finding = next(item for item in result.findings if item.code == "condition_conflict")
    assert "overcast" in finding.evidence.lower()
    assert "sun" in finding.evidence.lower()
    assert "flicker" in finding.message


@pytest.mark.parametrize("prompt", [
    "A static shot of a hallway with fast camera movement pushing in",
    "A locked-off wide of a kitchen; the camera whip-pans to the window",
])
def test_a_camera_described_two_ways_is_a_conflict(prompt):
    assert "camera_conflict" in prompt_check.review(prompt).codes


def test_minimal_camera_motion_beside_static_is_not_a_conflict():
    """The technical field of the skeleton says both, in every worked example.

    Reading "minimal camera motion" as a camera move would make the documented prompt
    shape self-contradictory.
    """
    result = prompt_check.review(WORKED_EXAMPLES["skeleton"])
    assert "camera_conflict" not in result.codes


def test_a_slow_push_in_on_a_face_is_allowed_but_an_orbit_is_not():
    """The authority-intro template calls for "static or very slow push-in" on a face.

    So the face check names the moves that distort — orbit, whip-pan, handheld — and
    leaves the one the document prescribes alone.
    """
    allowed = prompt_check.review(
        "An expert in a navy jacket settles into a chair; very slow push-in; three-point "
        "key; mood is calm authority; 16:9, 4 seconds, minimal motion.")
    assert "face_camera_move" not in allowed.codes

    refused = prompt_check.review(
        "An expert in a navy jacket in close-up; handheld camera drifting around her; "
        "three-point key; mood is calm authority; 16:9, 4 seconds.")
    assert "face_camera_move" in refused.codes


# -------------------------------------------------------------- on-screen text


@pytest.mark.parametrize("prompt", [
    "A document with the words 'BENEFITS SUSPENDED' clearly visible",
    "A newspaper headline that reads about the collapse",
    "A folder labelled \"CASE FILE 1997\" on a desk",
    "A bank statement with the number $4,500 shown",
    "A title card over the skyline",
    "A protest sign with SOLIDARITY FOREVER written across it",
])
def test_a_request_for_legible_type_is_blocked(prompt):
    result = prompt_check.review(prompt)
    assert "onscreen_text" in result.codes, prompt
    assert result.blocked is True
    assert "add the text in code" in result.summary()


def test_a_short_label_on_a_prop_is_not_a_text_request():
    """The mechanism-shot example animates a folder tab labelled "1997".

    A short label on a prop is what the document does; a sentence across the frame is
    what it warns about. A rule that cannot tell them apart forbids its own example.
    """
    assert "onscreen_text" not in prompt_check.review(
        WORKED_EXAMPLES["mechanism_diagram"]).codes


# ------------------------------------------------------------------- the specificity


def test_a_generic_prompt_names_the_fields_that_are_missing():
    result = prompt_check.review("A man at a desk doing finance stuff in an office.")
    finding = next(item for item in result.findings if item.code == "generic")
    assert "stuff" in finding.evidence
    for field in ("camera", "lighting", "mood"):
        assert field in finding.message
    # The number is the argument. "Be more specific" is advice; 85% against 30% is a
    # reason to spend two more minutes on the prompt.
    assert "85%" in finding.message


def test_a_realism_model_is_warned_about_a_stylized_prompt_and_a_stylized_one_is_not():
    stylized = ("A cel-shaded anime rooftop at dusk; static wide shot; neon key light; "
                "mood is defiant; 16:9, 5 seconds.")
    assert "register_mismatch" in prompt_check.review(
        stylized, model="fal-ai/veo3/image-to-video").codes
    assert "register_mismatch" in prompt_check.review(
        stylized, model="fal-ai/sora-2/image-to-video").codes
    # Same prompt, a model whose fingerprint is stylized work: nothing to say.
    assert "register_mismatch" not in prompt_check.review(
        stylized, model="fal-ai/lightricks/ltx-video-v2.3/image-to-video").codes
    # And an unnamed model cannot be judged, so it is not guessed at.
    assert "register_mismatch" not in prompt_check.review(stylized).codes


# ------------------------------------------------------------------- the report shape


def test_the_result_is_findings_rather_than_a_boolean():
    """A checker that answers False teaches callers to delete words until it answers True.

    What gets deleted is whichever half of the prompt was load-bearing.
    """
    result = prompt_check.review(
        "Two men fight in an alley, then one runs away; overcast night with bright "
        "sunlight; the words 'THE END' clearly visible.")
    assert isinstance(result.findings, tuple)
    assert len(result.findings) >= 4
    for finding in result.findings:
        assert finding.level in {"block", "warn"}
        assert finding.message
    # Blocking findings first: a caller showing one line shows the one that stops the
    # submission, not the advisory note that happened to be checked earlier.
    levels = [finding.level for finding in result.findings]
    assert levels == sorted(levels, key=lambda level: 0 if level == "block" else 1)

    payload = result.as_dict()
    assert payload["blocked"] is True
    assert {item["code"] for item in payload["findings"]} == set(result.codes)
