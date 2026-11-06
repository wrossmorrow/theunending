# frozen_string_literal: true

module Jekyll
  # One static page per poster set, at /printable/<name>/, built from
  # _data/unending-posters.json and joined to the post with the same filename
  # (e.g. 2026-09-12-computation). Nothing is written into the repo: pages
  # exist only in the build.
  #
  # Also exposes, for templates:
  #   site.data['poster_index']  newest-first list of sets (drives /printable/)
  #   post.data['printable_url'] on each post that has posters
  class PosterPagesGenerator < Generator
    safe true
    priority :normal

    def generate(site)
      posters = site.data['unending-posters'] || {}
      posts = site.posts.docs.each_with_object({}) { |p, h| h[p.basename_without_ext] = p }

      index = posters.map do |name, sizes|
        post = posts[name]
        Jekyll.logger.warn 'Posters:', "no post matches #{name}; using the name as title" unless post
        thumb = sizes.dig('18x24', 'thumb') || sizes.values.first['thumb']
        {
          'name'     => name,
          'title'    => post ? post.data['title'] : name,
          'date'     => post ? post.date : nil,
          'set'      => post ? post.data['set'] : nil,
          'post_url' => post ? post.url : nil,
          'image'    => post ? post.data['image'] : nil,
          'url'      => "/printable/#{name}/",
          'thumb'    => thumb
        }
      end
      # Newest first; the name (date-prefixed) breaks same-day ties stably.
      index.sort_by! { |e| [e['date'] || Time.at(0), e['name']] }.reverse!
      site.data['poster_index'] = index

      index.each_with_index do |e, i|
        posts[e['name']]&.data&.store('printable_url', e['url'])

        page = PageWithoutAFile.new(site, site.source, File.join('printable', e['name']), 'index.html')
        page.content = ''
        page.data.merge!(
          'layout'      => 'poster',
          'title'       => "#{e['title']} (printable)",
          'heading'     => e['title'],
          'description' => "Printable poster versions of “#{e['title']}” from The Unending.",
          'image'       => e['image'],
          'poster_name' => e['name'],
          'set'         => e['set'],
          'set_date'    => e['date'],
          'post_url'    => e['post_url'],
          'newer'       => i.positive? ? index[i - 1] : nil,
          'older'       => index[i + 1],
          'position'    => i + 1,
          'count'       => index.size
        )
        site.pages << page
      end
    end
  end
end
