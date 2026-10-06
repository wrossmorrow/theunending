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

{% for poster in site.data.unending-posters %}
  {% assign name = poster[0] %}
  {% assign post = site.posts | where_exp: "p", "p.path contains name" | first %}
  <section class="poster-row">
    <h3>
      {% if post %}<a href="{{ post.url | relative_url }}">{{ post.title }}</a>
      {% else %}{{ name }}{% endif %}
    </h3>
    <div class="poster-grid">
    {% for version in poster[1] %}
      {% assign size = version[0] %}
      {% assign p = version[1] %}
      {% if p.thumb.w <= p.thumb.h %}
      <figure>
      <a href="/assets/img/posters/{{ p.preview.src }}">
        <img src="/assets/img/posters/{{ p.thumb.src }}" width="{{ p.thumb.w }}" height="{{ p.thumb.h }}" loading="lazy" alt="{{ name }} ({{ size }})">
      </a>
      <figcaption>{{ size | replace: "x", " × " }}″</figcaption>
      </figure>
      {% endif %}
    {% endfor %}
    </div>
    {% for version in poster[1] %}
      {% assign size = version[0] %}
      {% assign p = version[1] %}
      {% if p.thumb.w > p.thumb.h %}
      <figure class="poster-wide">
        <a href="/assets/img/posters/{{ p.preview.src }}">
          <img src="/assets/img/posters/{{ p.thumb.src }}" width="{{ p.thumb.w }}" height="{{ p.thumb.h }}" loading="lazy" alt="{{ name }}, {{ size | replace: 'x', '×' }} in">
        </a>
        <figcaption>{{ size | replace: "x", " × " }}″</figcaption>
      </figure>
    {% endif %}
  {% endfor %}
  {% include poster-interest.html theme=post.set label="I like this one" cost_note="estimated for professional print on cold-press art paper" %}
  </section>
{% endfor %}

<dialog id="lightbox"><img alt=""></dialog>

<style>
.poster-grid { 
  display: grid; 
  grid-template-columns: repeat(4,1fr); 
  gap: 1rem; 
  max-width: 680px;
}
.poster-grid a {
  display:block;
  aspect-ratio:2/3; 
}
.poster-grid img {
  width:100%; height:100%;
  object-fit: contain;
  background: #fff;
  outline: 1px solid #eee;
}
.poster-row { margin: 2.5rem 0; }
.poster-row h3 { margin: 0 0 .75rem; }
.poster-grid figure { margin: 0; }
.poster-grid figcaption { margin-top: .4rem; font-size: .8rem; text-align: center; }
.poster-wide { margin: 1.5rem 0 0; }
.poster-wide img { 
  width: 100%; 
  height: auto; 
  background: #fff;
  outline: 1px solid #eee;
}
.poster-wide figcaption { margin-top: .4rem; font-size: .8rem; text-align: center; }

@media (max-width: 600px) { 
  .poster-grid { grid-template-columns: repeat(2, 1fr); } 
}

#lightbox {
  padding:0;
  border:0;
  background:none;
  overflow:hidden;
  max-width:none;
  max-height:none;
}
#lightbox::backdrop {
  background:rgba(0,0,0,.85);
}
#lightbox img {
  display:block;
  width:auto; 
  height:auto;
  max-width:90vw;
  max-height:90vh; max-height:90dvh;
  object-fit:contain;
}
</style>

<script>
const box = document.getElementById("lightbox"), big = box.querySelector("img");
document.querySelectorAll(".poster-grid a, .poster-wide a").forEach(a => a.addEventListener("click", e => {
  if (e.metaKey || e.ctrlKey) return;            // keep cmd/ctrl-click = new tab
  e.preventDefault();
  big.src = a.href;
  big.alt = a.querySelector("img").alt;
  box.showModal();                               // Esc closes it for free
}));
box.addEventListener("click", () => box.close()); // click anywhere to close
</script>
