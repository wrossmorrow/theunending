
site_s3_bucket := "theunending-ai-site-content-use1"
cloudfront_dist_id := "E134F26KPOO8Q5"

default:
    just --list

serve:
    bash scripts/build-landing-pool.sh
    bundle exec jekyll serve --livereload --drafts --future

build env="production":
    bash scripts/build-landing-pool.sh
    JEKYLL_ENV={{ env }} bundle exec jekyll build

# build, then upload without listing the whole bucket (never deletes); `just sync --dryrun` to preview
sync *args: build
    BUCKET={{ site_s3_bucket }} DIST={{ cloudfront_dist_id }} bash scripts/deploy.sh {{ args }}

# one small WebP per set (streams.yml `thumb:`) for the index; extra args pass through
thumbs *args:
    uv run scripts/make-index-thumbs.py {{ args }}
