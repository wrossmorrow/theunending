
default:
    just --list

serve:
    cd site && just serve
sync *args:
    cd site && just serve {{args}}
