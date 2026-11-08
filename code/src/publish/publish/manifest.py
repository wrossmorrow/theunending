from pydantic import BaseModel, ConfigDict


class SetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    set: str
    base: str
    manifest: str
    meta: str
    thumb: str


class DraftManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    set: str
    post_name: str
    post_draft: str
    image_manifest: list[str]
    set_spec: SetSpec
    posters_spec: dict
