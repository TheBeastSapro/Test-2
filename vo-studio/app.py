"""
ExplainTory VO Studio — local UI.

Gradio because Chatterbox already depends on it, so it costs no extra install, and
because a browser tab is a better home for a 12-minute render than a terminal.
Binds to localhost only: nothing here should be reachable from the network.

    python app.py          (or run.bat on Windows)
"""
import asyncio
import queue
import threading
from pathlib import Path

import gradio as gr

from vostudio import config, pipeline
from vostudio.voice_profile import VoiceProfile, apply_feedback
from vostudio.assistant import ask, check_auth

APP_ROOT = Path(__file__).resolve().parent
SETTINGS = config.Settings.load()
config.ensure_dirs()


class Log:
    """Collects pipeline output so a long render shows progress instead of a spinner."""

    def __init__(self):
        self.q: queue.Queue[str] = queue.Queue()
        self.lines: list[str] = []

    def __call__(self, msg: str):
        self.lines.append(str(msg))
        self.q.put(str(msg))

    def text(self) -> str:
        return "\n".join(self.lines[-400:])


def do_render(script_text, title, voice_file, exaggeration, effort_note, progress=gr.Progress()):
    if not script_text.strip():
        return "Paste a script first.", None
    if not voice_file:
        return ("No voice reference. Use the Voice tab — a clean 8-12 second clip of "
                "your own delivered read is the best reference you have."), None

    SETTINGS.generation.exaggeration = float(exaggeration)
    safe_title = "".join(c for c in (title or "Untitled") if c.isalnum() or c in " -_")
    project = config.PROJECTS_DIR / safe_title
    project.mkdir(parents=True, exist_ok=True)

    log = Log()
    result: dict = {}

    def work():
        try:
            result["r"] = pipeline.run(script_text, safe_title, Path(voice_file),
                                       SETTINGS, project, log=log)
        except Exception as exc:                       # surfaced, never swallowed
            log(f"FAILED: {type(exc).__name__}: {exc}")
            result["error"] = exc

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    while thread.is_alive():
        thread.join(timeout=0.5)
        progress(0.5, desc="rendering")
        yield log.text(), None
    thread.join()

    r = result.get("r")
    if r is None or r.final_path is None:
        yield log.text(), None
        return

    summary = [
        f"{r.title} — {r.duration_s/60:.0f}:{r.duration_s%60:05.2f}",
        f"{r.sections} sections, {r.chunks} chunks, {r.rerolled} re-rolled",
    ]
    if r.unresolved:
        summary.append(f"NEEDS AN EAR — {len(r.unresolved)} chunk(s) never passed "
                       f"the read-check: {r.unresolved}")
    summary += r.notes
    yield log.text() + "\n\n" + "\n".join(summary), str(r.final_path)


def do_assistant(message, history, mode):
    if not message.strip():
        return history, ""
    status = check_auth()
    if not status.ok:
        return history + [(message, status.detail)], ""

    chunks: list[str] = []
    asyncio.run(ask(message, APP_ROOT, on_text=chunks.append, permission_mode=mode))
    return history + [(message, "".join(chunks) or "(no output)")], ""


# ---------------------------------------------------------------- Voice Lab
SAMPLE_TEXT = (
    "The most spectacular story in this video is the one nobody can prove. "
    "In 1798, a French army landed in Egypt to cut England off from India."
)


def lab_render(profile_name, reference, sample_text):
    """
    Render ~10 seconds at the current settings. Short on purpose.

    Judging a voice on a full script wastes a render per round; the dial-in loop
    only works if a round costs seconds.
    """
    if not reference:
        return None, "Upload a reference clip on the Voice tab first.", ""
    prof = VoiceProfile.load(config.VOICES_DIR, profile_name or "default")
    prof.reference = reference

    from vostudio.generate import Generator
    gen = Generator(SETTINGS)
    out = config.VOICES_DIR / (profile_name or "default") / "sample.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        gen.generate_chunk(sample_text or SAMPLE_TEXT, reference, out,
                           exaggeration=prof.exaggeration,
                           temperature=prof.temperature,
                           cfg_weight=prof.cfg_weight,
                           speed=prof.speed)
    finally:
        gen.unload()
    return str(out), f"Current: {prof.summary()}", ""


def lab_feedback(profile_name, reference, sample_text, feedback, log):
    """His sentence in; moved numbers and a fresh sample out."""
    prof = VoiceProfile.load(config.VOICES_DIR, profile_name or "default")
    prof, changes = apply_feedback(prof, feedback)
    prof.reference = reference or prof.reference
    prof.save(config.VOICES_DIR)

    entry = f"> {feedback}\n" + "\n".join(f"    {c}" for c in changes)
    audio, summary, _ = lab_render(profile_name, reference, sample_text)
    return audio, summary, (log + "\n\n" + entry).strip(), ""


def lab_lock(profile_name):
    prof = VoiceProfile.load(config.VOICES_DIR, profile_name or "default")
    path = prof.save(config.VOICES_DIR)
    SETTINGS.active_profile = prof.name
    SETTINGS.generation.exaggeration = prof.exaggeration
    SETTINGS.generation.cfg_weight = prof.cfg_weight
    SETTINGS.generation.temperature = prof.temperature
    SETTINGS.save()
    return (f"Locked '{prof.name}'.\n{prof.summary()}\n\nSaved to {path}\n"
            f"Every render from now on uses it until you change it.")


with gr.Blocks(title="ExplainTory VO Studio") as demo:
    gr.Markdown("# ExplainTory VO Studio\nLocal Chatterbox rendering. No credits, no API key.")

    with gr.Tab("Voice"):
        gr.Markdown(
            "Chatterbox clones zero-shot from a reference clip. **The best reference "
            "you have is your own delivered read** — 8–12 seconds of clean speech, no "
            "music, no room tone. A cut of a finished voiceover works well.\n\n"
            "The clone drifts across a long script more than a trained ElevenLabs "
            "voice does. That is the tradeoff for free generation, and the read-check "
            "is what catches it."
        )
        voice = gr.Audio(label="Reference clip", type="filepath")

    with gr.Tab("Render"):
        title = gr.Textbox(label="Video title", placeholder="Every Drug Used in War Explained")
        script = gr.Textbox(label="Script", lines=18,
                            placeholder="Paste the script.\n\nA line on its own with "
                                        "three words or fewer and no full stop is "
                                        "treated as a chapter header.")
        with gr.Row():
            exaggeration = gr.Slider(0.25, 0.9, value=0.5, step=0.05,
                                     label="Exaggeration (0.5 = neutral read)")
            effort_note = gr.Textbox(label="Note to self", scale=2)
        go = gr.Button("Render", variant="primary")
        out_log = gr.Textbox(label="Progress", lines=18, max_lines=18)
        out_file = gr.Audio(label="Finished voiceover", type="filepath")
        go.click(do_render, [script, title, voice, exaggeration, effort_note],
                 [out_log, out_file])

    with gr.Tab("Voice Lab"):
        gr.Markdown(
            "**Dial the voice in by ear, the way you did in Rookcast.** Render ten "
            "seconds, say what is wrong in plain English, and the settings move. "
            "Repeat until it is right, then lock it.\n\n"
            "Words this understands: *flat · too expressive · too fast · too slow · "
            "false pauses · no natural gaps · doesn't sound like me · inconsistent · "
            "stiff · repeating*. Steps are deliberately small — big jumps overshoot "
            "and cost you a round walking them back."
        )
        with gr.Row():
            prof_name = gr.Textbox(label="Profile name", value="explaintory", scale=1)
            lab_summary = gr.Textbox(label="Current settings", interactive=False, scale=2)
        lab_text = gr.Textbox(label="Sample line", value=SAMPLE_TEXT, lines=2)
        with gr.Row():
            btn_sample = gr.Button("Render sample", variant="primary")
            btn_lock = gr.Button("Lock this profile")
        lab_audio = gr.Audio(label="Sample", type="filepath")
        lab_fb = gr.Textbox(label="What is wrong with it?",
                            placeholder="e.g. feels bit fast and a little flat")
        lab_log = gr.Textbox(label="Rounds", lines=12, interactive=False)

        btn_sample.click(lab_render, [prof_name, voice, lab_text],
                         [lab_audio, lab_summary, lab_fb])
        lab_fb.submit(lab_feedback, [prof_name, voice, lab_text, lab_fb, lab_log],
                      [lab_audio, lab_summary, lab_log, lab_fb])
        btn_lock.click(lab_lock, [prof_name], [lab_summary])

    with gr.Tab("Assistant"):
        auth = check_auth()
        gr.Markdown(
            ("**Signed in via your Claude subscription.**" if auth.ok
             else f"**Not ready.**\n\n```\n{auth.detail}\n```")
            + "\n\nClaude can read and edit this app, confined to its own folder with "
              "networking off. It ships asking before every edit — an agent with "
              "unattended write access to the pipeline that renders your audio is not "
              "a convenience worth defaulting into."
        )
        mode = gr.Radio(["default", "acceptEdits", "plan"], value="default",
                        label="Permission mode",
                        info="default = ask every time · acceptEdits = edits without "
                             "asking · plan = propose only, change nothing")
        chat = gr.Chatbot(height=420)
        msg = gr.Textbox(label="Ask for a change", placeholder="e.g. raise the WER threshold and explain the risk")
        msg.submit(do_assistant, [msg, chat, mode], [chat, msg])

if __name__ == "__main__":
    # localhost only, and never share=True — this exposes a filesystem-editing agent.
    demo.launch(server_name="127.0.0.1", inbrowser=True, share=False)
