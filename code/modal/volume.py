
import modal


models = [
    'black-forest-labs/FLUX.1-schnell',
    'black-forest-labs/FLUX.2-klein-4B',
    'timm/PE-Core-L-14-336',
]

app = modal.App("theunending-volume")

vol = modal.Volume.from_name("hf-hub-cache", create_if_missing=True)


@app.function(
    image=modal.Image.from_name(name="theunending").env({"HF_HOME": "/cache"}),
    volumes={"/cache": vol},
    secrets=[modal.Secret.from_name("huggingface-secret")],
    timeout=1500,
)
def preload_models():
    import os
    from huggingface_hub import snapshot_download

    for model in models:
        snapshot_download(
            repo_id=model,
            token=os.environ['HF_TOKEN'],
        )

    vol.commit()


@app.local_entrypoint()
def main():
    preload_models.remote()
