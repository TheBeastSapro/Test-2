"""Offline providers: deterministic, free, and they emit real media files.

This is not a test double bolted on afterwards — it is load-bearing product
infrastructure. It means the graph engine, the gates, the renderer, the billing
math and the UI can all be developed and demoed without an API key or a cent of
spend, and it gives every paying user a dry-run mode.

Determinism comes from seeding on the prompt hash, so the same run replays the
same output.
"""

from __future__ import annotations

import hashlib
import json
import re
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw

from ..render import ffmpeg as ff
from .base import (
    AvatarProvider,
    ImageProvider,
    LLMProvider,
    MediaResult,
    TextResult,
    VideoProvider,
    VoiceProvider,
)

WORDS_PER_SECOND = 2.6

_PALETTE = [
    (16, 24, 32),
    (34, 40, 68),
    (68, 32, 48),
    (24, 56, 56),
    (56, 48, 24),
    (40, 24, 64),
]


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)


def _hint_int(prompt: str, key: str, default: int) -> int:
    """Pull a number out of the JSON that nodes embed in their prompts."""
    match = re.search(rf'"{key}"\s*:\s*(\d+)', prompt)
    return int(match.group(1)) if match else default


class MockLLM(LLMProvider):
    name = "mock-llm"

    async def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        json_object: bool = False,
        schema_name: str = "",
    ) -> TextResult:
        seed = _seed(system + prompt)
        payload = self._fixture(schema_name, prompt, seed)
        text = json.dumps(payload, indent=2) if json_object else self._prose(prompt, seed)
        return TextResult(
            text=text,
            credits=0,
            provider=self.name,
            model="mock-1",
            meta={"schema_name": schema_name, "seed": seed, "mock": True},
        )

    # -- fixtures ---------------------------------------------------------------

    def _fixture(self, schema_name: str, prompt: str, seed: int) -> dict:
        topic = self._topic(prompt)
        builder = {
            "brief": self._brief,
            "script": self._script,
            "thumbnail": self._thumbnail,
            "broll_plan": self._broll,
            "compliance": self._compliance,
            "metadata": self._metadata,
            "research_queries": self._research_queries,
            "research_claims": self._research_claims,
        }.get(schema_name, self._generic)
        return builder(topic, prompt, seed)

    @staticmethod
    def _topic(prompt: str) -> str:
        match = re.search(r'"topic"\s*:\s*"([^"]{2,120})"', prompt)
        if match:
            return match.group(1)
        match = re.search(r"TOPIC:\s*(.+)", prompt)
        if match:
            return match.group(1).strip()[:120]
        first = next((ln.strip() for ln in prompt.splitlines() if ln.strip()), "Untitled")
        return first[:120]

    def _brief(self, topic: str, prompt: str, seed: int) -> dict:
        target = _hint_int(prompt, "target_duration_seconds", 480)
        beats = max(4, min(12, target // 60))
        return {
            "working_title": f"{topic}: What Nobody Tells You",
            # Four devices rather than four phrasings, so the picker at the brief gate
            # can be seen doing its job offline — a mock that answers with one title
            # four times would render a chooser with nothing to choose between.
            "title_options": [
                {"title": f"{topic}: What Nobody Tells You",
                 "device": "withheld outcome",
                 "why": "Names the gap without promising a number the video has to hit."},
                {"title": f"The Real Reason {topic}",
                 "device": "single cause",
                 "why": "Commits to one explanation, which the beat outline can deliver."},
                {"title": f"{topic} — And Why It Keeps Happening",
                 "device": "stated stake",
                 "why": "Says the recurrence is the story, not the incident."},
                {"title": f"What Actually Happens When {topic}",
                 "device": "mechanism",
                 "why": "Promises the how, which is what the middle beats are."},
            ],
            "angle": f"A grounded, evidence-first walk through {topic.lower()}.",
            "audience": "Curious adults who want substance without filler",
            "hook": f"Most explanations of {topic.lower()} skip the part that matters.",
            "promise": "Three concrete takeaways and one thing to do today.",
            "target_duration_seconds": target,
            "beats": [
                {
                    "name": f"Beat {i + 1}",
                    "purpose": ["hook", "context", "mechanism", "evidence", "payoff"][i % 5],
                    "summary": f"Point {i + 1} about {topic.lower()}.",
                }
                for i in range(beats)
            ],
            "keywords": [topic.lower(), "explained", "documentary", "deep dive"],
            "mock": True,
        }

    def _script(self, topic: str, prompt: str, seed: int) -> dict:
        target = _hint_int(prompt, "target_duration_seconds", 480)
        scene_count = max(4, min(14, target // 45))
        per_scene = target / scene_count
        words_per_scene = max(12, int(per_scene * WORDS_PER_SECOND))
        scenes = []
        for i in range(scene_count):
            narration = self._narration(topic, i, words_per_scene, seed)
            scenes.append(
                {
                    "index": i,
                    "narration": narration,
                    "visual_prompt": (
                        f"cinematic establishing shot illustrating {topic.lower()}, "
                        f"beat {i + 1}, moody lighting, shallow depth of field"
                    ),
                    "visual_kind": "video" if i % 3 == 0 else "image",
                    "seconds": round(len(narration.split()) / WORDS_PER_SECOND, 2),
                    "on_screen_text": f"Point {i + 1}" if i else "",
                }
            )
        return {
            "title": f"{topic}: What Nobody Tells You",
            "description": textwrap.shorten(
                f"A clear, careful look at {topic}. Chapters, sources and takeaways below.",
                width=400,
            ),
            "tags": [topic.lower(), "explained", "deep dive", "documentary"],
            "scenes": scenes,
            "word_count": sum(len(s["narration"].split()) for s in scenes),
            "mock": True,
        }

    @staticmethod
    def _narration(topic: str, index: int, words: int, seed: int) -> str:
        openers = [
            f"Here is the part of {topic.lower()} that usually gets left out.",
            f"To see why that matters, look at how {topic.lower()} actually works.",
            f"The evidence on {topic.lower()} is more specific than the headlines suggest.",
            f"Consider what changes once you take {topic.lower()} seriously.",
            f"That brings us to the practical side of {topic.lower()}.",
        ]
        filler = (
            "The mechanism is simple once stated plainly, and the consequences follow "
            "from it directly. What looks like an exception is usually the rule seen "
            "from an unfamiliar angle, which is why the details are worth the minute "
            "it takes to walk through them carefully and without shortcuts. "
        )
        text = openers[(index + seed) % len(openers)] + " " + filler * 6
        return " ".join(text.split()[:words])

    def _thumbnail(self, topic: str, prompt: str, seed: int) -> dict:
        return {
            "concepts": [
                {
                    "prompt": f"bold high-contrast thumbnail about {topic}, dramatic rim light, "
                              f"single subject, negative space on the left",
                    "text_overlay": topic.upper()[:24],
                    "rationale": "Face-free, single focal point, readable at 168px wide.",
                },
                {
                    "prompt": f"minimal graphic thumbnail for {topic}, two-tone palette, "
                              f"large numeral, heavy shadow",
                    "text_overlay": "THE REAL REASON",
                    "rationale": "Curiosity gap without clickbait overpromise.",
                },
            ],
            "mock": True,
        }

    def _broll(self, topic: str, prompt: str, seed: int) -> dict:
        count = max(1, len(re.findall(r'"index"\s*:\s*\d+', prompt)) or 6)
        return {
            "shots": [
                {
                    "scene_index": i,
                    "prompt": f"documentary b-roll for {topic.lower()}, shot {i + 1}, "
                              f"natural light, slow camera move",
                    "kind": "video" if i % 3 == 0 else "image",
                    "motion": "slow push in" if i % 2 else "gentle pan right",
                }
                for i in range(count)
            ],
            "mock": True,
        }

    def _compliance(self, topic: str, prompt: str, seed: int) -> dict:
        return {
            "verdict": "pass",
            "issues": [],
            "checks": {
                "reused_content": "original narration",
                "medical_financial_claims": "none detected",
                "copyright_risk": "no third-party footage referenced",
                "advertiser_friendly": "no profanity or graphic content",
                "disclosure_required": False,
            },
            "mock": True,
        }

    def _metadata(self, topic: str, prompt: str, seed: int) -> dict:
        return {
            "title": f"{topic}: What Nobody Tells You"[:100],
            "description": f"A careful look at {topic}.\n\nChapters:\n00:00 Intro",
            "tags": [topic.lower(), "explained", "deep dive"],
            "category_id": "27",
            "privacy_status": "private",
            "mock": True,
        }

    def _research_queries(self, topic: str, prompt: str, seed: int) -> dict:
        return {
            "queries": [
                f"{topic} explained",
                f"{topic} statistics data",
                f"{topic} recent developments 2026",
                f"{topic} criticism counterargument",
            ],
            "open_questions": [
                f"How often does {topic.lower()} actually happen?",
                f"Who bears the cost of {topic.lower()}?",
            ],
            "mock": True,
        }

    def _research_claims(self, topic: str, prompt: str, seed: int) -> dict:
        """Claims quoted verbatim from the supplied page text.

        The quote is lifted from the real `page_text` in the prompt rather than
        invented, because the research engine verifies quotes by substring match. A
        mock that returned plausible-sounding quotes would fail that check and make
        the offline flow look broken when it is working correctly.
        """
        match = re.search(r'"page_text"\s*:\s*"(.*?)"\s*[,}]', prompt, re.DOTALL)
        page_text = (match.group(1) if match else "").replace("\\n", " ")
        words = page_text.split()
        if len(words) < 12:
            return {"claims": [], "mock": True}

        span = " ".join(words[:18])
        return {
            "claims": [
                {
                    "text": f"[MOCK CLAIM] The source discusses {topic.lower()}.",
                    "quote": span,
                    "kind": "context",
                    "confidence": "low",
                }
            ],
            "mock": True,
        }

    def _generic(self, topic: str, prompt: str, seed: int) -> dict:
        return {"topic": topic, "result": "ok", "seed": seed, "mock": True}

    @staticmethod
    def _prose(prompt: str, seed: int) -> str:
        return (
            "This is deterministic mock prose standing in for a model response. "
            f"Prompt fingerprint {seed:x}."
        )


class MockVoice(VoiceProvider):
    name = "mock-voice"

    async def list_voices(self) -> list[dict]:
        """Mirror the catalogue so name resolution can be exercised offline."""
        from ..voice.catalogue import STOCK_VOICES

        return [
            {
                "voice_id": f"mock-{voice.name.lower()}",
                "name": voice.name,
                "category": "premade",
                "labels": {"accent": voice.accent, "energy": voice.energy},
                "preview_url": None,
            }
            for voice in STOCK_VOICES
        ]

    async def synthesize(
        self, text: str, *, voice_id: str, out_path: Path, speed: float = 1.0
    ) -> MediaResult:
        words = max(len(text.split()), 1)
        seconds = round(words / (WORDS_PER_SECOND * max(speed, 0.1)), 2)
        out_path = out_path.with_suffix(".m4a")
        # An audible low tone: proves the audio track is really wired through.
        ff.make_tone_audio(out_path, seconds, frequency=180 + (_seed(voice_id or "v") % 90))
        return MediaResult(
            path=out_path,
            mime="audio/mp4",
            credits=0,
            provider=self.name,
            duration_seconds=seconds,
            meta={"words": words, "voice_id": voice_id, "mock": True},
        )


class MockImage(ImageProvider):
    name = "mock-image"

    async def generate(
        self, prompt: str, *, out_path: Path, width: int = 1280, height: int = 720
    ) -> MediaResult:
        out_path = out_path.with_suffix(".png")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        seed = _seed(prompt)
        base = _PALETTE[seed % len(_PALETTE)]
        image = Image.new("RGB", (width, height), base)
        draw = ImageDraw.Draw(image)

        # Cheap deterministic geometry so consecutive plates look different.
        for i in range(6):
            offset = ((seed >> (i * 3)) % max(width // 2, 1)) + i * 40
            shade = tuple(min(255, c + 18 * (i + 1)) for c in base)
            draw.ellipse(
                [offset, height // 4 + i * 12, offset + width // 3, height - i * 18],
                outline=shade,
                width=3,
            )
        caption = "\n".join(textwrap.wrap(prompt[:180], width=44)[:5])
        draw.multiline_text((40, 40), caption, fill=(235, 235, 235), spacing=6)
        image.save(out_path, "PNG", optimize=True)

        return MediaResult(
            path=out_path,
            mime="image/png",
            credits=0,
            provider=self.name,
            meta={"width": width, "height": height, "mock": True},
        )


class MockVideo(VideoProvider):
    name = "mock-video"

    async def generate_clip(
        self,
        prompt: str,
        *,
        out_path: Path,
        seconds: float = 5.0,
        width: int = 1280,
        height: int = 720,
        image_path: Path | None = None,
    ) -> MediaResult:
        out_path = out_path.with_suffix(".mp4")
        if image_path and Path(image_path).exists():
            ff.still_to_clip(Path(image_path), out_path, seconds, width=width, height=height)
        else:
            red, green, blue = _PALETTE[_seed(prompt) % len(_PALETTE)]
            hex_colour = f"0x{red:02x}{green:02x}{blue:02x}"
            ff.make_color_clip(
                out_path, seconds, width=width, height=height, color=hex_colour,
                label=prompt[:70],
            )
        return MediaResult(
            path=out_path,
            mime="video/mp4",
            credits=0,
            provider=self.name,
            duration_seconds=seconds,
            meta={"prompt": prompt[:200], "mock": True},
        )


class MockAvatar(AvatarProvider):
    name = "mock-avatar"

    async def generate(
        self,
        *,
        audio_path: Path,
        avatar_id: str,
        out_path: Path,
        width: int = 1280,
        height: int = 720,
    ) -> MediaResult:
        seconds = ff.ffprobe_duration(Path(audio_path)) if Path(audio_path).exists() else 5.0
        out_path = out_path.with_suffix(".mp4")
        ff.make_color_clip(
            out_path,
            seconds,
            width=width // 2,
            height=height // 2,
            color="0x2b2b3a",
            label=f"avatar {avatar_id or 'default'}",
        )
        return MediaResult(
            path=out_path,
            mime="video/mp4",
            credits=0,
            provider=self.name,
            duration_seconds=seconds,
            meta={"avatar_id": avatar_id, "mock": True},
        )
