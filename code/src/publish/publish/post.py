from json import dumps


def post_draft(
    title: str,
    subtitle: str,
    date: str,
    set: str,
    model: str,
    extra_details: str | None = None,
) -> str:
    # NOTE: make sure no leading space/newline jekyll will barf
    post_lines = [
        "---",
        "layout: post",
        f"title: {dumps(title)}",
        f"subtitle: {dumps(subtitle)}",
        f"date: {date}",
        "categories: [unending]",
        f"set: {set}",
        f"image: assets/og/{set}.jpg",
    ]
    extra = (extra_details or "").strip()
    if extra:
        post_lines.append(f"extra: {dumps(extra)}")
    post_lines += [
        "---",
        "",
        "{% include image-stream.html set=page.set cols=5 rows=6 interval=500 %}",
        "",
        "---",
        "",
        "<small>",
        f"Created with [{model}](https://huggingface.co/{model}). Similarities in modals ",
        "defined by embeddings from [perception encoder](https://huggingface.co/facebook/PE-Core-L14-336). ",
        "All computed on an A100 instance in modal.",
        "</small>",
    ]
    return "\n".join(post_lines) + "\n"
