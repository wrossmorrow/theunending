---
layout: default
title: Printable
description: Printable collections of The Unending images
permalink: /printable/
---

{% include image-stream.html set="all" axis="x" cols=8 sample=40 interval=1500 %}

---

These are randomly drawn grids of images made for the "unending" pages. Each is titled, sized, and dated at generation time. The _actual_ "printable" images are "large" (easily 10's of megabytes) and not fair to put on a webpage, and not scaled to represent actual size. You can use the image squares as a gauge, every square is 1.5" x 1.5". Due to scaling none of the thumbs (obviously) or previews are fully faithful to the printable source images. I'm looking into being able to generate one on demand for download or printing. 

{% include poster-interest.html %}

<link rel="stylesheet" href="{{ '/assets/css/posters.css' | relative_url }}?v={{ site.time | date: '%s' }}">

<div class="poster-index" id="printables" data-batch="24" data-batch-narrow="12">
{%- for e in site.data.poster_index %}
  <a class="poster-tile" href="{{ e.url | relative_url }}">
    <img src="{{ '/assets/img/posters/' | append: e.thumb.src | relative_url }}" width="{{ e.thumb.w }}" height="{{ e.thumb.h }}" loading="lazy" alt="">
    <span class="poster-tile-title">{{ e.title }}</span>
  </a>
{%- endfor %}
</div>

<script src="{{ '/assets/js/show-more.js' | relative_url }}?v={{ site.time | date: '%s' }}" defer></script>
