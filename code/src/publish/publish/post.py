from json import dumps
from textwrap import dedent


def post_draft(
    title: str,
    subtitle: str,
    date: str,
    set: str,
    model: str,
    extra_details: str | None = None,
) -> str:
    # NOTE: make sure no leading space/newline jekyll will barf
    post = dedent(f"""
    ---
    layout: post
    title: {dumps(title)}
    subtitle: {dumps(subtitle)}
    date: {date}
    categories: [unending]
    set: {set}
    image: assets/og/{set}.jpg
    ---

    {{% include image-stream.html set=page.set cols=5 rows=6 interval=500 %}}

    ---

    <small>
    Created with [{model}](https://huggingface.co/{model}). Similarities in modals 
    defined by embeddings from [perception encoder](https://huggingface.co/facebook/PE-Core-L14-336). 
    All computed on an A100 instance in modal.
    </small>
    """).lstrip()

    extra = (extra_details or "").strip()
    if not extra:
        return post
    return f"{post}\n<small>\n{extra}\n</small>\n"
