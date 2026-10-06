# frozen_string_literal: true

# ArtworkXMP
# ==========
#
# Reads IPTC Extension "artwork or object" metadata out of a JPEG's embedded
# XMP packet. Pure Ruby -- only REXML from the stdlib. Nothing to install, no
# exiftool binary needed at build time.
#
# This complements exifr rather than replacing it: exifr reads the EXIF/TIFF
# segment (capture date, camera, exposure), this reads the XMP segment (titles,
# artist, medium, keywords). They are different parts of the same file.
#
#   require_relative 'artwork_xmp'
#
#   meta = ArtworkXMP.read('photo.jpg')
#   meta['ArtworkTitle']                 #=> "Nocturne No. 3"
#   meta['ArtworkCreator']               #=> ["Ada Lorne"]
#   meta['ArtworkPhysicalDescription']   #=> "Oil on linen, 60 x 90 cm"
#   meta['Subject']                      #=> ["night", "studio"]
#
# Keys match the names ExifTool uses, so they line up with the editor's panel
# and with anything you already do via `exiftool -j`. Absent fields are simply
# missing from the hash (use #read_with_defaults if you want every key present).
#
# List-valued fields (ArtworkCreator, ArtworkStyleperiod, Creator, Subject)
# always come back as Arrays. Everything else is a String.

require 'rexml/document'

module ArtworkXMP
  # --- namespaces ---------------------------------------------------------
  RDF_NS      = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
  IPTCEXT_NS  = 'http://iptc.org/std/Iptc4xmpExt/2008-02-29/'
  DC_NS       = 'http://purl.org/dc/elements/1.1/'
  PHOTOSHOP_NS = 'http://ns.adobe.com/photoshop/1.0/'
  XMP_NS      = 'http://ns.adobe.com/xap/1.0/'

  XMP_APP1_HEADER = "http://ns.adobe.com/xap/1.0/\0"
  XMP_EXT_HEADER  = "http://ns.adobe.com/xmp/extension/\0"

  # --- field maps ---------------------------------------------------------
  # The XMP property names are NOT the friendly names ExifTool prints.
  # ExifTool's "ArtworkTitle" is really Iptc4xmpExt:ArtworkOrObject -> AOTitle.
  ARTWORK_FIELDS = {
    'AOTitle'                    => 'ArtworkTitle',
    'AOCreator'                  => 'ArtworkCreator',
    'AODateCreated'              => 'ArtworkDateCreated',
    'AOCircaDateCreated'         => 'ArtworkCircaDateCreated',
    'AOPhysicalDescription'      => 'ArtworkPhysicalDescription',
    'AOContentDescription'       => 'ArtworkContentDescription',
    'AOStyleperiod'              => 'ArtworkStyleperiod',
    'AOSource'                   => 'ArtworkSource',
    'AOSourceInvNo'              => 'ArtworkSourceInventoryNo',
    'AOSourceInvURL'             => 'ArtworkSourceInvURL',
    'AOCopyrightNotice'          => 'ArtworkCopyrightNotice',
    'AOCurrentCopyrightOwnerName' => 'ArtworkCurrentCopyrightOwnerName',
    'AOCurrentLicensorName'      => 'ArtworkCurrentLicensorName',
    'AOCreatorId'                => 'ArtworkCreatorID'
  }.freeze

  GENERAL_FIELDS = {
    [DC_NS, 'title']            => 'Title',
    [DC_NS, 'creator']          => 'Creator',
    [DC_NS, 'description']      => 'Description',
    [DC_NS, 'subject']          => 'Subject',
    [DC_NS, 'rights']           => 'Rights',
    [PHOTOSHOP_NS, 'Headline']  => 'Headline',
    [PHOTOSHOP_NS, 'Credit']    => 'Credit',
    [PHOTOSHOP_NS, 'DateCreated'] => 'DateCreated',
    [XMP_NS, 'Rating']          => 'Rating'
  }.freeze

  # Fields that should always be Arrays, even with a single value.
  LIST_FIELDS = %w[ArtworkCreator ArtworkStyleperiod Creator Subject].freeze

  ALL_KEYS = (ARTWORK_FIELDS.values + GENERAL_FIELDS.values).freeze

  class << self
    # Main entry point. Returns a Hash of String => (String | Array<String>).
    # Returns {} for a file with no XMP, or one that can't be parsed.
    # Never raises on a malformed file -- a bad JPG shouldn't break your build.
    def read(path)
      packet = extract_packet(path)
      return {} if packet.nil? || packet.empty?

      parse(packet)
    rescue StandardError
      {}
    end

    # Same, but every known key is present (nil / [] when absent). Handy in
    # Liquid, where a missing key and an empty one behave differently.
    def read_with_defaults(path)
      found = read(path)
      ALL_KEYS.each_with_object({}) do |key, out|
        out[key] = found.fetch(key, LIST_FIELDS.include?(key) ? [] : nil)
      end
    end

    # Parse an XMP packet you already have as a String.
    def parse(xml)
      doc = REXML::Document.new(xml)
      out = {}
      collect_general(doc.root, out)
      collect_artwork(doc.root, out)
      out
    rescue StandardError
      {}
    end

    # ---------------------------------------------------------------------
    # Packet extraction
    # ---------------------------------------------------------------------

    # Pull the <x:xmpmeta> packet out of a JPEG by walking its segment markers.
    # Falls back to scanning the raw bytes, which also covers TIFF/PNG/WebP and
    # any file where the packet isn't in a standard APP1 segment.
    def extract_packet(path)
      data = File.binread(path)
      from_jpeg_segments(data) || scan_bytes(data)
    rescue StandardError
      nil
    end

    private

    def from_jpeg_segments(data)
      return nil unless data[0, 2] == "\xFF\xD8".b

      pos = 2
      while pos < data.bytesize - 4
        return nil unless data.getbyte(pos) == 0xFF

        marker = data.getbyte(pos + 1)
        pos += 2

        # Standalone markers carry no payload.
        next if marker == 0x01 || (marker >= 0xD0 && marker <= 0xD9)
        # Start of scan -- image data follows, no more metadata segments.
        break if marker == 0xDA

        length = (data.getbyte(pos) << 8) | data.getbyte(pos + 1)
        break if length < 2

        payload = data[pos + 2, length - 2]
        pos += length

        next unless marker == 0xE1 && payload

        if payload.start_with?(XMP_APP1_HEADER.b)
          return payload[XMP_APP1_HEADER.bytesize..].force_encoding('UTF-8')
        end
        # Extended XMP holds overflow for very large packets (rare, and never
        # for artwork fields) -- deliberately ignored.
        next if payload.start_with?(XMP_EXT_HEADER.b)
      end
      nil
    end

    def scan_bytes(data)
      text = data.force_encoding('UTF-8')
      start = text.index('<x:xmpmeta')
      start ||= text.index('<rdf:RDF')
      return nil unless start

      finish = text.index('</x:xmpmeta>', start)
      finish = finish ? finish + '</x:xmpmeta>'.length
                      : text.index('</rdf:RDF>', start)&.+('</rdf:RDF>'.length)
      return nil unless finish

      text[start...finish]
    end

    # ---------------------------------------------------------------------
    # Parsing
    # ---------------------------------------------------------------------

    def collect_artwork(root, out)
      node = find_element(root) do |el|
        el.namespace == IPTCEXT_NS && el.name == 'ArtworkOrObject'
      end
      return unless node

      # ArtworkOrObject is a Bag of structs. In practice there's one entry, so
      # we read the first; change this to map over `items` for multi-artwork.
      bag = child_elements(node).find do |c|
        c.namespace == RDF_NS && %w[Bag Seq Alt].include?(c.name)
      end
      items = bag ? child_elements(bag).select { |li| li.namespace == RDF_NS && li.name == 'li' } : [node]
      entry = items.first
      return unless entry

      # Struct members appear either as child elements or, in RDF shorthand,
      # as attributes on the li. Both are valid; different apps write different
      # ones, so check both.
      entry.attributes.each_attribute do |attr|
        key = ARTWORK_FIELDS[attr.name]
        next unless key && attr.namespace == IPTCEXT_NS

        store(out, key, attr.value)
      end

      child_elements(entry).each do |el|
        key = ARTWORK_FIELDS[el.name]
        next unless key && el.namespace == IPTCEXT_NS

        store(out, key, value_of(el))
      end
    end

    def collect_general(root, out)
      each_element(root) do |el|
        key = GENERAL_FIELDS[[el.namespace, el.name]]
        store(out, key, value_of(el)) if key

        # rdf:Description shorthand: <rdf:Description photoshop:Credit="..."/>
        next unless el.namespace == RDF_NS && el.name == 'Description'

        el.attributes.each_attribute do |attr|
          akey = GENERAL_FIELDS[[attr.namespace, attr.name]]
          store(out, akey, attr.value) if akey
        end
      end
    end

    # An XMP value is one of: a plain literal, a lang-alt (rdf:Alt, pick
    # x-default), or an ordered/unordered list (rdf:Seq / rdf:Bag).
    def value_of(el)
      container = child_elements(el).find do |c|
        c.namespace == RDF_NS && %w[Alt Seq Bag].include?(c.name)
      end

      unless container
        text = el.text
        return nil if text.nil?

        stripped = text.strip
        return stripped.empty? ? nil : stripped
      end

      items = child_elements(container).select { |c| c.namespace == RDF_NS && c.name == 'li' }
      values = items.map { |li| li.text.to_s.strip }.reject(&:empty?)

      if container.name == 'Alt'
        preferred = items.find { |li| li.attributes['xml:lang'] == 'x-default' }
        text = (preferred || items.first)&.text.to_s.strip
        text.empty? ? nil : text
      else
        values.empty? ? nil : values
      end
    end

    def store(out, key, value)
      return if key.nil? || value.nil?
      return if value.respond_to?(:empty?) && value.empty?

      out[key] = if LIST_FIELDS.include?(key)
                   Array(value)
                 elsif value.is_a?(Array)
                   value.first
                 else
                   value
                 end
    end

    # --- small REXML helpers ------------------------------------------------
    # REXML::Elements isn't reliably Enumerable across versions, so go via to_a.

    def child_elements(el)
      el.elements.to_a
    end

    def each_element(el, &block)
      return unless el

      block.call(el)
      child_elements(el).each { |c| each_element(c, &block) }
    end

    def find_element(el, &pred)
      return nil unless el
      return el if pred.call(el)

      child_elements(el).each do |c|
        found = find_element(c, &pred)
        return found if found
      end
      nil
    end
  end
end

# Run directly to inspect a file:  ruby artwork_xmp.rb photo.jpg
if $PROGRAM_NAME == __FILE__
  require 'json'
  ARGV.each do |file|
    puts "== #{file}"
    puts JSON.pretty_generate(ArtworkXMP.read(file))
  end
end
