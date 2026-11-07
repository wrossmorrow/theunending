from json import dumps
from textwrap import dedent


def post_draft(
    title: str,
    subtitle: str,
    date: str,
    set: str,
    model: str,
) -> str:
    # NOTE: make sure no leading space/newline jekyll will barf
    return dedent(f"""
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
