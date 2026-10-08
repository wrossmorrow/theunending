
site_s3_bucket := "theunending-ai-site-content-use1"
cloudfront_dist_id := "E134F26KPOO8Q5"

default:
    just --list

serve:
    bundle exec jekyll serve --livereload --drafts --future

build env="production":
    JEKYLL_ENV={{env}} bundle exec jekyll build

sync: build
    aws s3 sync _site/ s3://{{site_s3_bucket}}/ # --delete
    aws cloudfront create-invalidation --distribution-id {{cloudfront_dist_id}} --paths "/*"
