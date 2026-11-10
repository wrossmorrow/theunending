"""Generate The Unending pipeline flow diagrams as standalone SVGs."""

W = 1240
FONT = "Inter, 'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', Menlo, Consolas, monospace"

INK = "#1f2328"
MUTED = "#57606a"
LINE = "#6e7781"
BG = "#ffffff"
GRID = "#e6e8eb"

KINDS = {
    # fill, stroke, kicker colour
    "ui": ("#f6f8fa", "#57606a", "#57606a"),
    "api": ("#eef4ff", "#3b6fd8", "#3b6fd8"),
    "gpu": ("#fff4e8", "#d9822b", "#b5651d"),
    "cpu": ("#f1f8ee", "#4a9a3c", "#3d7f31"),
    "store": ("#f7f2fc", "#8a5cc7", "#7448ad"),
    "ext": ("#f6f8fa", "#8c959f", "#57606a"),
}


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class D:
    def __init__(self, title, subtitle, height):
        self.title, self.subtitle, self.h = title, subtitle, height
        self.parts = []
        self.nodes = {}

    def node(self, key, x, y, w, h, kind, kicker, title, lines=(), shape="rect"):
        fill, stroke, kc = KINDS[kind]
        self.nodes[key] = (x, y, w, h)
        r = h / 2 if shape == "pill" else 12
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
        )
        cx = x + w / 2
        ty = y + 34 if kicker else y + h / 2 - 8 * len(lines)
        if kicker:
            self.parts.append(
                f'<text x="{cx}" y="{ty}" text-anchor="middle" font-family="{FONT}" '
                f'font-size="11" font-weight="700" letter-spacing="1.2" fill="{kc}">{esc(kicker.upper())}</text>'
            )
            ty += 24
        self.parts.append(
            f'<text x="{cx}" y="{ty}" text-anchor="middle" font-family="{FONT}" '
            f'font-size="17" font-weight="600" fill="{INK}">{esc(title)}</text>'
        )
        for i, ln in enumerate(lines):
            mono = ln.startswith("`")
            t = ln.strip("`")
            self.parts.append(
                f'<text x="{cx}" y="{ty + 22 + 19*i}" text-anchor="middle" '
                f'font-family="{MONO if mono else FONT}" font-size="{12.5 if mono else 13.5}" '
                f'fill="{MUTED}">{esc(t)}</text>'
            )

    def anchor(self, key, side, t=0.5):
        x, y, w, h = self.nodes[key]
        return {
            "l": (x, y + h * t),
            "r": (x + w, y + h * t),
            "t": (x + w * t, y),
            "b": (x + w * t, y + h),
        }[side]

    def path(self, pts, label=None, lpos=None, dashed=False, both=False, anchor="middle"):
        d = "M" + " L".join(f"{px} {py}" for px, py in pts)
        dash = ' stroke-dasharray="6 5"' if dashed else ""
        start = ' marker-start="url(#ah-s)"' if both else ""
        self.parts.append(
            f'<path d="{d}" fill="none" stroke="{LINE}" stroke-width="2" '
            f'stroke-linejoin="round"{dash}{start} marker-end="url(#ah)"/>'
        )
        if label:
            lx, ly = lpos
            for i, ln in enumerate(label.split("\n")):
                self.parts.append(
                    f'<text x="{lx}" y="{ly + 16*i}" text-anchor="{anchor}" font-family="{FONT}" '
                    f'font-size="13" fill="{MUTED}" paint-order="stroke" stroke="{BG}" '
                    f'stroke-width="5" stroke-linejoin="round">{esc(ln)}</text>'
                )

    def svg(self):
        dots = (
            f'<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
            f'<circle cx="2" cy="2" r="1.1" fill="{GRID}"/></pattern>'
        )
        markers = (
            f'<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">'
            f'<path d="M0 0 L10 5 L0 10 z" fill="{LINE}"/></marker>'
            f'<marker id="ah-s" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="8" markerHeight="8" orient="auto">'
            f'<path d="M10 0 L0 5 L10 10 z" fill="{LINE}"/></marker>'
        )
        head = (
            f'<rect width="{W}" height="{self.h}" fill="{BG}"/>'
            f'<rect width="{W}" height="{self.h}" fill="url(#dots)"/>'
            f'<text x="40" y="52" font-family="{FONT}" font-size="24" font-weight="700" fill="{INK}">{esc(self.title)}</text>'
            f'<text x="40" y="78" font-family="{FONT}" font-size="14.5" fill="{MUTED}">{esc(self.subtitle)}</text>'
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{self.h}" '
            f'viewBox="0 0 {W} {self.h}"><defs>{dots}{markers}</defs>{head}'
            + "".join(self.parts)
            + "</svg>\n"
        )


def legend(d, y):
    x = 40
    items = [("solid", "request / data"), ("dashed", "status callbacks")]
    for style, text in items:
        dash = ' stroke-dasharray="6 5"' if style == "dashed" else ""
        d.parts.append(
            f'<path d="M{x} {y} L{x+34} {y}" stroke="{LINE}" stroke-width="2"{dash} marker-end="url(#ah)"/>'
            f'<text x="{x+44}" y="{y+4.5}" font-family="{FONT}" font-size="12.5" fill="{MUTED}">{text}</text>'
        )
        x += 190


# Column layout shared by all three diagrams
BW, BH = 200, 130
C = [40, 360, 680, 1000]
M = [(C[i] + BW + C[i+1]) / 2 for i in range(3)]  # gap midpoints


def drafting():
    d = D("Drafting", "Create a set, name it, evaluate prompts and review 3×3 draft grids", 470)
    y = 130
    d.node("ui", C[0], y, BW, BH, "ui", "browser", "Admin UI", ["set creation", "drafting · preview"])
    d.node("api", C[1], y, BW, BH, "api", "EC2 · envoy auth", "Admin API", ["FastAPI + Postgres", "outbox → relay"])
    d.node("gpu", C[2], y, BW, BH, "gpu", "modal · L40S", "GPU job", ["evaluation", "3×3 draft grid"])
    d.node("s3", C[3], y, BW, BH, "store", "S3 · staging", "Draft images", ["`<bucket>/drafts/`"], shape="store")

    d.path([d.anchor("ui", "r", .35), d.anchor("api", "l", .35)], "create · draft", (M[0], y + 36))
    d.path([d.anchor("api", "l", .65), d.anchor("ui", "r", .65)], "presigned URL", (M[0], y + 112))
    d.path([d.anchor("api", "r", .35), d.anchor("gpu", "l", .35)], "dispatch", (M[1], y + 36))
    d.path([d.anchor("gpu", "l", .65), d.anchor("api", "r", .65)], "status", (M[1], y + 112), dashed=True)
    d.path([d.anchor("gpu", "r"), d.anchor("s3", "l")], "upload", (M[2], y + 57))

    sx, _ = d.anchor("s3", "b")
    ux, _ = d.anchor("ui", "b")
    yb = y + BH + 70
    d.path([(sx, y + BH), (sx, yb), (ux, yb), (ux, y + BH)],
           "browser fetches previews directly with the signed URL", ((sx + ux) / 2, yb - 10))
    legend(d, 430)
    return d


def commit():
    d = D("Commit", "A draft is accepted; the batch generates the full set with embeddings", 520)
    y = 130
    d.node("ui", C[0], y, BW, BH, "ui", "browser", "Admin UI", ["commit draft", "progress · retry"])
    d.node("api", C[1], y, BW, BH, "api", "EC2 · envoy auth", "Admin API", ["run state + events", "outbox → relay"])
    d.node("gpu", C[2], y, BW, BH, "gpu", "modal · L40S / A100", "GPU batch job", ["5000 images", "letterbox rejects · embeddings"])
    d.node("s3", C[3], y, BW, BH + 30, "store", "S3 · staging", "Set run", ["`runs/<hash>/*.png`", "`embeddings.npy`", "`rejected/`"], shape="store")
    d.node("sns", C[1] + 20, y + BH + 90, BW - 40, 56, "ext", "", "SNS email", [], shape="pill")

    d.path([d.anchor("ui", "r", .35), d.anchor("api", "l", .35)], "commit", (M[0], y + 36))
    d.path([d.anchor("api", "l", .65), d.anchor("ui", "r", .65)], "progress (poll)", (M[0], y + 112))
    d.path([d.anchor("api", "r", .35), d.anchor("gpu", "l", .35)], "dispatch", (M[1], y + 36))
    d.path([d.anchor("gpu", "l", .65), d.anchor("api", "r", .65)], "progress", (M[1], y + 112), dashed=True)
    d.path([d.anchor("gpu", "r"), (C[3], y + 65)], "upload", (M[2], y + 57))
    d.path([d.anchor("api", "b"), d.anchor("sns", "t")], "status changes", (430, y + BH + 50), anchor="start")
    legend(d, 480)
    return d


def publish():
    d = D("Publish", "A completed set becomes site assets and a post PR; merging deploys it", 720)
    y = 130
    d.node("ui", C[0], y, BW, BH, "ui", "browser", "Admin UI", ["publish set", "extra details"])
    d.node("api", C[1], y, BW, BH, "api", "EC2 · envoy auth", "Admin API", ["publish run", "outbox → relay"])
    d.node("job", C[2], y, BW, BH, "cpu", "ECS fargate", "Publish task", ["posters · OG · thumbs", "similars · manifest"])
    d.node("stg", C[3], y - 40, BW, 100, "store", "S3 · staging", "Set run", ["`runs/<hash>/`"], shape="store")
    d.node("site", C[3], y + 110, BW, 110, "store", "S3 · site (write-once)", "Site assets", ["`assets/img/…`", "`assets/streams/…`"], shape="store")
    y2 = y + BH + 150
    d.node("gh", C[2], y2, BW, BH - 20, "ext", "github", "Site repo PR", ["`_posts/ · _data/set_*`", "review → merge"])
    d.node("gha", C[3], y2 + 130, BW, BH - 10, "ext", "github actions", "Build & deploy", ["landing pool · Jekyll", "sync · CloudFront inval."])

    d.path([d.anchor("ui", "r", .35), d.anchor("api", "l", .35)], "publish", (M[0], y + 36))
    d.path([d.anchor("api", "l", .65), d.anchor("ui", "r", .65)], "progress (poll)", (M[0], y + 112))
    d.path([d.anchor("api", "r", .35), d.anchor("job", "l", .35)], "ECS RunTask", (M[1], y + 36))
    d.path([d.anchor("job", "l", .65), d.anchor("api", "r", .65)], "status", (M[1], y + 112), dashed=True)

    # staging -> job (read)
    d.path([d.anchor("stg", "l"), (C[2] + BW + 40, y + 10), (C[2] + BW + 40, y + 30), (C[2] + BW, y + 30)],
           "read", (M[2] + 8, y + 2))
    # job -> site (write)
    d.path([(C[2] + BW, y + 100), (C[2] + BW + 40, y + 100), (C[2] + BW + 40, y + 165), d.anchor("site", "l")],
           "write", (M[2] + 8, y + 148))
    # job -> gh PR
    d.path([d.anchor("job", "b"), d.anchor("gh", "t")], "open PR", (C[2] + BW / 2 + 10, y + BH + 80), anchor="start")
    # gh -> gha (merge)
    gx = C[2] + BW / 2
    d.path([d.anchor("gh", "b"), (gx, y2 + 195), (C[3], y2 + 195)], "on merge", (gx + 12, y2 + 150), anchor="start")
    # gha -> site
    d.path([d.anchor("gha", "t"), d.anchor("site", "b")], "deploy", (C[3] + BW / 2 + 10, y2 + 50), anchor="start")
    legend(d, 690)
    return d


if __name__ == "__main__":
    for name, fn in [("1-drafting", drafting), ("2-commit", commit), ("3-publish", publish)]:
        with open(f"{name}.svg", "w") as f:
            f.write(fn().svg())
        print("wrote", name)
