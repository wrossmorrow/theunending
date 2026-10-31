
import modal


if __name__ == "__main__":

    app = modal.App.lookup("theunending", create_if_missing=True)

    img = (
        modal.Image.debian_slim(python_version="3.12")
        .uv_sync()
        .env({"HF_HOME": "/cache"})
    )

    with modal.enable_output():
        img.build(app).publish("theunending")
