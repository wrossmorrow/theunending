# frozen_string_literal: true

module Jekyll
  # Per-set data files, merged into the structures the templates already read.
  #
  #   _data/set_streams/<post-name>.json   {"set": "<key>", "base": ..., "manifest": ..., "meta": ..., "thumb": ...}
  #       -> site.data['streams']['sets'][<key>]   (minus "set")
  #   _data/set_posters/<post-name>.json   {"12x18": {...}, "18x24": {...}, ...}
  #       -> site.data['unending-posters'][<post-name>]
  #
  # <post-name> is the post's filename without extension (e.g. 2026-09-12-computation).
  # The stream key comes from "set" inside the file, not the filename, because a
  # set's key and its post name can differ (modern-painting-flux2 lives under
  # 2026-10-05-modern-painting).
  #
  # One file per set means a publish only ever adds files: nothing shared to
  # merge-conflict on. streams.yml keeps `defaults` (and may still hold legacy
  # `sets`); a key defined in both places is an error, not a silent override.
  #
  # Runs before every other generator (poster_pages.rb reads unending-posters),
  # and generators run before any Liquid renders.
  class SetDataGenerator < Generator
    safe true
    priority :highest

    def generate(site)
      merge_streams(site)
      merge_posters(site)
    end

    private

    def merge_streams(site)
      files = site.data['set_streams'] || {}
      streams = (site.data['streams'] ||= {})
      sets = (streams['sets'] ||= {})

      files.each do |name, cfg|
        where = "_data/set_streams/#{name}.json"
        raise Errors::FatalException, "#{where}: expected a JSON object" unless cfg.is_a?(Hash)

        key = cfg['set']
        raise Errors::FatalException, "#{where}: missing \"set\" (the stream key)" if key.nil? || key.to_s.empty?
        raise Errors::FatalException, "#{where}: set \"#{key}\" is already defined" if sets.key?(key)

        sets[key] = cfg.reject { |k, _| k == 'set' }
      end
    end

    def merge_posters(site)
      files = site.data['set_posters'] || {}
      posters = (site.data['unending-posters'] ||= {})

      files.each do |name, sizes|
        where = "_data/set_posters/#{name}.json"
        unless sizes.is_a?(Hash)
          raise Errors::FatalException,
                "#{where}: expected a JSON object of sizes (got #{sizes.class}; an array wrapper is not allowed)"
        end
        raise Errors::FatalException, "#{where}: posters \"#{name}\" are already defined" if posters.key?(name)

        posters[name] = sizes
      end
    end
  end
end
