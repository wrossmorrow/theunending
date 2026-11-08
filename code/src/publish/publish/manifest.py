from pydantic import BaseModel


class SetSpec(BaseModel):
    thumb: str
    set: str
    manifest: str
    meta: str


class DraftManifest(BaseModel):
    set: str
    post_name: str
    post_draft: str
    image_manifest: list[str]
    set_spec: SetSpec
    posters_spec: dict
