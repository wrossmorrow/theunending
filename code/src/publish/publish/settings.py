"""Settings for the Unending Backend/Pipelining."""

from datetime import datetime
from functools import cached_property
from json import dumps, loads
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class Run(BaseModel):
    run_id: UUID
    set_id: UUID
    type: Literal["PUBLISH"]  # also BATCH, EVALUATION; but require PUBLISH
    status: Literal["PENDING"]  # others, but require PENDING


class Set(BaseModel):
    set_id: UUID
    model: str
    prompt: str
    model_prompt_hash: str
    slug: str
    name: str
    status: Literal["PUBLISHING"]  # others, but require PUBLISHING


class PublishSettings(BaseSettings):
    """Settings for the Unending Backend/Pipelining."""

    # required, not defaultable; keep ADMIN_API_TOKEN in env

    RUN_ID: UUID
    ADMIN_API_TOKEN: str

    # needed, but defaultable

    ADMIN_API_HOST: str = "https://admin.theunending.ai"
    POST_DATE: str = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
    RAW_BUCKET: str = "wrossmorrow-genai-repetitions-use1"
    SITE_BUCKET: str = "theunending-ai-site-content-use1"

    MAX_S3_THREADS: int = 32

    IMAGES_DIR: str = "images"
    SIMILAR_DIR: str = "similar"
    OG_TILE_DIR: str = "og"
    POSTERS_DIR: str = "posters"

    # github app (for draft pull requests)

    GITHUB_API_BASE_URL: str = "https://api.github.com"
    GITHUB_APP_ID: str
    GITHUB_APP_CLIENT_ID: str
    GITHUB_APP_INSTALLATION_ID: str
    GITHUB_APP_PRIVATE_KEY: str
    GITHUB_REPO_OWNER: str
    GITHUB_REPO_NAME: str

    # derived (including from API call responses)

    @property
    def ADMIN_API_URL(self) -> str:
        return f"{self.ADMIN_API_HOST}/api/v0/runs/{self.RUN_ID}/status"

    @cached_property
    def RUN(self) -> Run:
        response = httpx.get(
            url=f"{self.ADMIN_API_HOST}/api/v0/runs/{self.RUN_ID}",
            headers={
                "authorization": f"Bearer {self.ADMIN_API_TOKEN}",
            },
        )
        response.raise_for_status()
        return Run.model_validate(response.json())

    @property
    def SET_ID(self) -> UUID:
        return self.RUN.set_id

    @cached_property
    def SET(self) -> Set:
        response = httpx.get(
            url=f"{self.ADMIN_API_HOST}/api/v0/sets/{self.SET_ID}",
            headers={
                "authorization": f"Bearer {self.ADMIN_API_TOKEN}",
            },
        )
        response.raise_for_status()
        return Set.model_validate(response.json())

    @property
    def MODEL_ID(self) -> str:
        return self.SET.model

    @property
    def PROMPT(self) -> str:
        return self.SET.prompt

    @property
    def MODEL_PROMPT_HASH(self) -> str:
        return self.SET.model_prompt_hash

    @property
    def SET_NAME(self) -> str:
        return self.SET.slug

    @property
    def POST_TITLE(self) -> str:
        return self.SET.name

    @property
    def POST_NAME(self) -> str:
        return f"{self.POST_DATE}-{self.SET_NAME}"

    @property
    def SET_SPEC(self) -> dict:
        return {
            "base": f"https://theunending.ai/assets/img/{self.POST_NAME}/",
            "manifest": f"assets/streams/{self.SET_NAME}.json",
            "meta": f"/assets/img/{self.POST_NAME}/{{id}}.json",
        }

    # raw source(s)

    @property
    def RAW_PREFIX(self) -> str:
        return f"runs/{self.MODEL_PROMPT_HASH}"

    @property
    def RAW_IMG_ASSETS(self) -> str:
        return f"s3://{self.RAW_BUCKET}/{self.RAW_PREFIX}"

    # site target(s)

    @property
    def SITE_IMG_ASSETS_PREFIX(self) -> str:
        return f"assets/img/{self.POST_NAME}"

    SITE_OG_IMAGE_PREFIX: str = "assets/og"

    @property
    def SITE_POSTER_RAW_PREFIX(self) -> str:
        return f"assets/img/posters/raw/{self.POST_NAME}"

    @property
    def SITE_POSTER_PREVIEW_PREFIX(self) -> str:
        return f"assets/img/posters/previews/{self.POST_NAME}"

    @property
    def SITE_POSTER_THUMBS_PREFIX(self) -> str:
        return f"assets/img/posters/thumbs/{self.POST_NAME}"

    # verbose stuff about posters

    POSTER_SIZES_JSON: str = dumps(
        {
            "12x18": "portrait",
            "18x24": "portrait",
            "24x36": "portrait",
            "36x48": "portrait",
            "40x80": "landscape",
        }
    )

    POSTER_PREVIEW_SIZE_PREVIEW_WH_LOOKUP: dict = {
        "12x18": {
            "w": 1600,
            "h": 2400,
        },
        "18x24": {
            "w": 1800,
            "h": 2400,
        },
        "24x36": {
            "w": 1600,
            "h": 2400,
        },
        "36x48": {
            "w": 1800,
            "h": 2400,
        },
        "40x80": {
            "w": 2400,
            "h": 1200,
        },
    }

    POSTER_THUMB_SIZE_PREVIEW_WH_LOOKUP: dict = {
        "12x18": {
            "w": 600,
            "h": 900,
        },
        "18x24": {
            "w": 675,
            "h": 900,
        },
        "24x36": {
            "w": 600,
            "h": 900,
        },
        "36x48": {
            "w": 675,
            "h": 900,
        },
        "40x80": {
            "w": 900,
            "h": 450,
        },
    }

    @property
    def POSTER_SIZES(self) -> dict:
        return loads(self.POSTER_SIZES_JSON)

    @property
    def POSTERS_SPEC(self) -> dict:
        return ({size: self._poster_spec(size) for size in self.POSTER_SIZES},)

    def _poster_spec(self, size: str) -> dict:
        return {
            "name": self.POST_NAME,
            "size": size,
            "preview": {
                "src": f"previews/{self.POST_NAME}/{size}.webp",
                **self.POSTER_PREVIEW_SIZE_PREVIEW_WH_LOOKUP[size],
            },
            "thumb": {
                "src": f"thumbs/{self.POST_NAME}/{size}.webp",
                **self.POSTER_THUMB_SIZE_PREVIEW_WH_LOOKUP[size],
            },
        }
