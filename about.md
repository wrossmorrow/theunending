---
layout: default
title: About
description: Discussion about what The Unending is
permalink: /about/
---

{% include image-stream.html set="all" axis="x" cols=8 sample=40 interval=1500 %}

---

I should probably explain what this is about. If you're looking it can obviously be about anything you like, not only my half-baked view. I have to admit I also believe explaining at all defeats the purpose. Or maybe put another way if I _have_ to explain I've failed in communicating whatever it is I'm trying to find already. And any explanation somewhat presumes there is a purpose past general interest or boredom. 

I also have a "rule" I've used in my (art)work sometimes: if I'm not myself a little confused and uncertain, especially "halfway through," its not going far enough. That's probably applicable here. I'm not sure what's happening, I'm not sure its interesting, and if so exactly how. I'm uncomfortable, in part, just doing it as using AI for art production is a bit frought. Its undeniably "here" though. Maybe that alone is part of my goal, exploring that discomfort. 

You can adopt this perspective too. Meaning, you can just like (or not like) any of this from your gut just as well. We're not doing science here, we don't have to prove anything.

In any case, the relevant pages on this site being explained are:
<ul>
{% for post in site.categories.unending %}
    {% if post.url != page.url %}
    <li>
    <span style="color: #666;">{{ post.date | date: "%Y-%m-%d" }}</span> — 
    <a href="{{ post.url | relative_url }}">{{ post.title }} (<small>{{ post.subtitle | truncate: 40, "..." }}</small>)</a>
    </li>
    {% endif %}
{% endfor %}
</ul>

If you would rather not poison your views of these pages, [get out]({{ site.baseurl }}/).

---

Generative images, in the sense of digital visual content, are here. Not like, here here, as in this page/site though they are, but like "in the system," certainly on social media, many advertisements, and probably inside many workplaces. Specifically what we can do is the following: write some text (sometimes of semi-structured format) or supply some sample images and get "digital images" as a result. "Digital images" are pixel-value arrays that can be transmitted easily over computer networks and rendered on displays effectively anywhere in the world. 

I am exploring several aspects of generative images that I guess, by definition, are interesting to me: 
* Turning text into digital images is relatively cheap (thousands of images for a few dollars in an hour or less)
* Variations, minor or major, on a theme are abundant (automatic, automatable, abundant)
* The themes chosen can be nearly arbitrary (though I find quality varies wildly)

Based on these features the explorations in these pages first explicitly trade off quality for quantity. That there are too many, "unending", variations on a given theme of hopefully-apparently-cheap quality (each) is the point. By being of copious volume, any given image alone probably feels diminished; cheap abundance should by nature be devaluing. So if it feels confusingly cheap or vacuous while presented in a possibly overwhelming way that's probably a good thing. 

Minor variations/variability achievable are also subtly interesting, I think, especially if almost imperceptible. In contrast to "real" works, where minor variations would be both laborious and presumably futile, often connoting "drafts" to select from based on criteria unidentified _a priori_, minor variations feel effectively "free" through pseudo-randomness and potentially unjudgeable. I can't help think of Warhol prints, but I'm not conciously trying to draw a pop art parallel even if inevitable. 

If you click on an image and see the "similar" results, 

![similar]({{ "assets/img/about/similar.jpg" | relative_url }}){:width="75%"}

you can evaluate uniqueness yourself. If the stream has an exact duplicate image, it is guaranteed to appear there. And it likely won't.

I'm occasionally playing with arbitrary themes too. That's more "traditional" and worth less explanation being closer to how you yourself reflect on the specific content of a given image. If so, the content and the titles should work together to point out what I'm exploring. This all sounds objectively silly and I know that; in fact I hope you can find some humor hiding in some of the themes.

So, besides exploring what I can find in being able to generate digital images, maybe "as a medium," I am curious about the specific format communicating an accompanying sense of drowning in a content stream we can't stop of cheap variations of visually rendered ideas. To be clear, I hope this _isn't_ a medium for one-off substitutes for human production, and that's not the proposal. The voluminous production, the minor variations, the unstoppability, feels aligned with the expectations around these tools, what the zeitgeist (so to speak) behind them points to.

---

There's something particularly evocative, to me at least, about the inexpensive and relentless volume. In contrast larger, single images don't quite do it. Consider

![memento mori]({{ "assets/img/about/single-graffiti-painting.png" | relative_url }}){:width="75%"}

or 

![old computers]({{ "assets/img/about/single-old-computers.png" | relative_url }}){:width="75%"}

or 

![old masters]({{ "assets/img/about/single-old-masters.png" | relative_url }}){:width="75%"}

They're maybe interesting for a few seconds but ultimately obviously disposable. If anything compositional is interesting at all it's from uncanny physical inaccuracies slightly confounding interpretation. Maybe a best case outcome is any given image feels vapid and its the presentation emphasizing the character of the approach in which they're shown. That is, I think any single image misses the "volumetric" axis of generative AI. 

Here's a format I think is _perhaps_ suitable for physical printing with a potentially related effect. This one is a 24"x36" ready preparation (a pretty normal hanging picture or poster size) with 260 1.5" square images:

<div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; width: 100%;">
  <img src="{{ 'assets/img/about/dress-code-24x36.webp' | relative_url }}" alt="dress code" style="width: 100%; height: auto; object-fit: contain; outline: 1px solid #eee;" />
  <img src="{{ 'assets/img/about/burnt-sockets-24x36.webp' | relative_url }}" alt="burnt sockets" style="width: 100%; height: auto; object-fit: contain; outline: 1px solid #eee;" />
</div>

I have at least drafted prints like this:

<div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; width: 100%;">
  <img src="{{ 'assets/img/about/memento-mori-24x36.webp' | relative_url }}" alt="memento mori" style="width: 100%; aspect-ratio: 2 / 3; object-fit: cover; display: block; outline: 1px solid #eee;" />
  <img src="{{ 'assets/img/about/memento-mori-printed.jpg' | relative_url }}" alt="second image" style="width: 100%; aspect-ratio: 2 / 3; object-fit: cover; display: block;" />
</div>

Maybe unrealistically large such compositions like 40"x80" (slightly larger than a twin XL bed) with 1104 1.5" square images do a bit better:

![desert-rocks]({{ "assets/img/about/desert-rocks-40x80.webp" | relative_url }}){:width="75%"}

I'm not sure analogue media are able to translate a dynamic sense of "unending" off a screen, but it would have to be many of these disposable single variations at once. In any case, [here is a blast of printable style representations]({% link printable.md %}).

---

So all of these examples intend to be an illusion of a truly unending stream (and an uncontrollable one at that, if you didn't notice). Posing an "illusion" is actually apt, and  of what I think is happening anyway. Hopefully you don't take that knowledge as deflating, though that happens easily;  even if you know you can still value enough to maybe even give me some feedback. If you think the explanation ruins the effect scroll up, close the page, or [get out]({{ site.baseurl }}/).

These pages loop through a shuffled pre-computed array of images randomized on every page load. This array is large, typically 5000 unique images/image-variations are pre-computed for a given prompt. Creating these takes maybe a few dollars and a few hours with open (and freely licensed) models. Given the size and rate of image population it would still take a reasonable fraction of an hour to see them all, you'd download about a gigabyte of data (so heads up), and the variations should be observably different even though closely related. I would posit the stream is _perceptually_ unending, if not precisely infinite, as I'd challenge someone to perceptually identify looping without counting. One could, in principle, create a functionally unending stream running these works a different way reserving persistent compute for generation and calling up new images without end. I kind of like faking it with scale though.

As for "practice", almost none of these are "one-shots" as we might say; you might be able to guess the rare lucky ones. Any one case here probably takes 1/2 hour to an hour of futzing around with various prompts to use over time, reflecting on the results and iterating until it feels right-ish. I'd guess around 50% of prompt ideas tried make the cut with many dropped almost immediately.

---

<small>Claude (Opus 5, medium) wrote the most of the code for the site. I'm not as interested in `js`/`jekyll` magic myself, and was a good use case for letting something else handle it.</small>

