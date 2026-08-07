from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration, read from the environment / .env file."""

    model_config = SettingsConfigDict(
        env_prefix="FORGECAST_", env_file=".env", extra="ignore"
    )

    secret_key: str = "dev-insecure-secret-change-me"
    encryption_key: str = ""
    database_url: str = "sqlite:///./forgecast.db"
    storage_dir: Path = Path("./storage")
    base_url: str = "http://localhost:8000"

    # Where the operator's own scripting documents live, read at prompt-build time by
    # `forgecast.scripting.library`.
    #
    # The default is deliberately in the home directory and not under `storage_dir`,
    # which is `./storage` and therefore inside the working tree. Those documents are
    # licensed to the operator and to nobody else, and a default that puts them in the
    # tree is a default that puts them in a commit and in the zip `tools/package.py`
    # builds — which is a thing that gets sent to other people. Outside the tree, the
    # accident cannot happen; `EXCLUDE` in the packager is the second lock, for a folder
    # somebody moves in by hand.
    #
    # The folder name is repeated rather than imported: `scripting.library` imports this
    # module, so importing it back would be a cycle. `tests/test_scripting.py` asserts
    # the two agree, which is what stops one of them being renamed alone.
    #
    # `Documents/`, not `~/Forgecast/`. The packaged archive's top-level directory is
    # `Forgecast/` and INSTALL.md says to unzip it anywhere you can write — so an
    # install unpacked in the home directory made this default a *child of the app
    # folder*: inside the agent's sandbox, inside what a hand-made zip of the app
    # folder contains, and inside the tree the packager walks. The guard test did not
    # catch it because it compared against the development checkout rather than against
    # a real install root. `library.directory()` refuses the folder outright if it still
    # resolves inside the app, which is the check that does not depend on a default
    # being chosen well.
    scripting_dir: Path = Path.home() / "Documents" / "Forgecast" / "scripting-library"

    # Which encoder renders this machine's video. "cpu", "nvidia" or "intel"; empty
    # means the app decides, which today means the CPU.
    #
    # A machine setting rather than a channel one, and the distinction is load-bearing:
    # the GPU belongs to the computer, not to the channel. A channel carried to a second
    # machine — or restored from a cloud backup onto one — must not arrive asking for an
    # encoder that machine does not have, and `Channel` is exactly what the backup
    # copies.
    #
    # An unavailable choice downgrades to the CPU rather than failing, so a wrong value
    # here costs a slower render and never a lost one. See `render.ffmpeg.resolve_encoder`.
    video_encoder: str = ""

    access_token_ttl_minutes: int = 60 * 24 * 7

    # Registration is closed by default. This is the one setting whose default has to
    # be the *restrictive* one: a private instance that becomes reachable — a tunnel, a
    # VPS, a forwarded port — must not accept strangers because nobody remembered to
    # turn signup off. Open it deliberately when you want other people on it, and
    # create your own account with `forgecast bootstrap`.
    allow_signup: bool = False

    # How long a signed media URL stays valid. Long enough to watch a render without
    # the link expiring mid-playback, short enough that a copied URL is not a
    # permanent key to the file.
    media_url_ttl_seconds: int = 60 * 60 * 6

    # ------------------------------------------------------------- desktop mode
    # Set by the desktop launcher, never edited by hand. It turns on two things that
    # only make sense when the server is a local application: the one-time sign-in
    # handoff (so double-clicking the icon does not land on a password prompt) and the
    # in-app Quit button. Both are refused for any request that did not arrive on the
    # loopback interface, so a tunnelled or forwarded port still gets the login page.
    local_mode: bool = False
    local_handoff_token: str = ""
    # The handoff is only accepted for this long after the process starts. The window
    # opens within a second or two; anything later is not the launcher.
    local_handoff_ttl_seconds: int = 300

    owner_email: str = ""
    owner_password: str = ""

    # ------------------------------------------------------------- cloud backup
    # Off, and the default has to be the restrictive one for the same reason
    # `allow_signup` does: an install that never asked for cloud backup must never open a
    # connection to GitHub, and "nobody remembered to turn it off" is not an acceptable
    # way for an operator's scripts to end up on someone else's service.
    #
    # This is the *seed* for a fresh install. The operator's own decision is recorded in
    # `storage/cloud.json` by `forgecast.cloud.config`, because a feature you enable by
    # editing `.env` is a feature that asks the operator to do exactly the thing this app
    # exists to avoid. Once that file exists, it wins.
    cloud_sync: bool = False

    # The OAuth app client ID used for the GitHub device flow. Not a secret — device flow
    # sends no client secret at all, which is the property that makes it the right choice
    # for an app that ships as a zip: the only GitHub credential in the archive is a
    # public identifier. Empty means this build has no app registered, and the feature
    # says so rather than showing a code that cannot work.
    github_client_id: str = ""

    # "mock" never touches the network and never spends money.
    provider_mode: Literal["mock", "live"] = "mock"

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    elevenlabs_api_key: str = ""
    # MiniMax narration. Separate from the agent's MiniMax sign-in on purpose: the
    # subscription covers the chat CLI, text-to-speech is billed against this key.
    minimax_api_key: str = ""
    fal_key: str = ""
    # `key:secret`, joined. Higgsfield's header is `Authorization: Key {id}:{secret}`, so
    # the pair is stored as one value rather than as two fields nobody would keep in sync.
    higgsfield_api_key: str = ""
    runway_api_key: str = ""
    heygen_api_key: str = ""

    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    # A Data API key, distinct from the OAuth pair above: the pair authorises uploads
    # to the operator's own channel, this reads public statistics for research.
    youtube_api_key: str = ""

    # Freesound, the middle tier of the sound-effect chain. Free, and the token meters
    # rather than bills — the same category as the Pexels key in `providers.footage`, so
    # it does not breach the rule that this app runs on subscriptions rather than on keys
    # that can run up a balance. Absent, and the chain simply skips that tier.
    freesound_api_key: str = ""

    # The two footage vendors that require a token. Same category as Freesound above and
    # for the same reason: both meter, neither bills, so a leaked or exhausted key costs
    # nothing but the lane. `config.py` already blesses that category by name.
    #
    # These decide whether the free lane can actually carry a video. NASA and Internet
    # Archive need no key and reach public-domain film, but they reach old film — a
    # channel about anything recent gets nothing from them. Pexels and Pixabay are where
    # a modern shot comes from, and without them the free lane exists and rarely wins.
    # Absent, `find` returns [] for those two sources rather than erroring, and the beat
    # falls through to generation exactly as it does today.
    pexels_api_key: str = ""
    pixabay_api_key: str = ""

    # Research search providers. Tavily is preferred when both are present because it
    # returns extracted page content, saving a fetch per result.
    tavily_api_key: str = ""
    brave_api_key: str = ""

    worker_concurrency: int = 2
    worker_poll_seconds: float = 2.0

    # Signup grant. Must cover at least one complete short run or the free tier is a
    # dead end — a 60s long-form run reserves ~260 credits, a Short ~150.
    signup_credit_grant: int = 400

    @property
    def is_mock(self) -> bool:
        return self.provider_mode == "mock"

    def platform_key(self, provider: str) -> str:
        return {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "elevenlabs": self.elevenlabs_api_key,
            "minimax": self.minimax_api_key,
            "fal": self.fal_key,
            "higgsfield": self.higgsfield_api_key,
            "runway": self.runway_api_key,
            "heygen": self.heygen_api_key,
            "tavily": self.tavily_api_key,
            "brave": self.brave_api_key,
        }.get(provider, "")

    def run_dir(self, run_id: int) -> Path:
        path = self.storage_dir / "runs" / str(run_id)
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    return settings
