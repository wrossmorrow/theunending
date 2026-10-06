require 'exifr/jpeg'

require_relative 'artwork_xmp'

module Jekyll
  class PhotoMetadataGenerator < Generator
    safe true
    priority :low

    def generate(site)
      site.posts.docs.each do |post|
        next unless post.data['image_dir']

        dir_path = File.join(site.source, post.data['image_dir'])
        next unless File.directory?(dir_path)

        photos = []
        
        # Use File::FNM_CASEFOLD and .uniq to prevent duplicate matches on macOS
        patterns = File.join(dir_path, '*.{jpg,jpeg}')
        files = Dir.glob(patterns, File::FNM_CASEFOLD).uniq.sort

        files.each do |img_path|
          filename = File.basename(img_path)
          caption = nil
          art_title = nil
          art_medium = nil
          art_dimensions = nil

          begin
            exif = EXIFR::JPEG.new(img_path)
            meta = ArtworkXMP.read(img_path)
            caption = exif.image_description if exif.exif?
            original_datetime = exif.date_time_original ? exif.date_time_original.to_s : nil
            art_title = meta['ArtworkTitle']
            art_medium, art_dimensions = meta['ArtworkPhysicalDescription']
              &.split(',', 2)
              &.map(&:strip)
          rescue => e
            Jekyll.logger.warn "EXIF Reader:", "Could not read #{img_path}: #{e.message}"
          end

          photos << {
            'file' => filename,
            'title'       => art_title,
            'medium'      => art_medium,
            'dimensions'  => art_dimensions,
            'description' => caption,
            'datetime'    => original_datetime
          }
        end

        post.data['extracted_photos'] = photos
      end
    end
  end
end
