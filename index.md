---
layout: default
title: Unending
---

{% include image-stream.html set="all" axis="x" cols=8 sample=40 interval=1500 %}

---

{% include index-cards.html %}

<!-- {% assign sorted_categories = site.categories | sort %}
{% for category in sorted_categories %}
  {% assign cat_code = category[0] %}
  {% assign cat_data = site.data.categories[cat_code] %}
  <ul>
    {% for post in category[1] %}
      <li>
        <span style="color: #666;">{{ post.date | date: "%Y-%m-%d" }}</span> — 
        <a href="{{ post.url | relative_url }}">{{ post.title }} (<small>{{ post.subtitle | truncate: 40, "..." }}</small>)</a>
      </li>
    {% endfor %}
  </ul>
{% endfor %} -->

---

{% include prompt-idea.html %}
