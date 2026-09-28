"""Generate every SVG used by the profile README (dark + light variants).

Edit the JSON files in assets/ and run:  python scripts/generate.py
The GitHub Action in .github/workflows/profile.yml runs this daily.

Set GITHUB_TOKEN (or GH_TOKEN) to also get contributions and streaks.
If the GitHub API fails, the existing stats/language/project cards are kept.
"""
import datetime as dt
import json
import math
import os
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
MONO = "Consolas, 'SF Mono', 'JetBrains Mono', 'Fira Code', monospace"
SANS = "ui-sans-serif, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"

# Dracula for dark, a readable "Dracula-on-paper" for light.
THEMES = {
    "dark": dict(
        bg="#282a36", panel="#21222c", border="#44475a", grid="#343746",
        fg="#f8f8f2", muted="#6272a4", purple="#bd93f9", pink="#ff79c6",
        cyan="#8be9fd", green="#50fa7b", yellow="#f1fa8c", orange="#ffb86c",
        red="#ff5555",
    ),
    "light": dict(
        bg="#ffffff", panel="#f6f8fa", border="#d0d7de", grid="#eaeef2",
        fg="#1f2328", muted="#656d76", purple="#7c3aed", pink="#db2777",
        cyan="#0891b2", green="#16a34a", yellow="#a16207", orange="#c2410c",
        red="#dc2626",
    ),
}

LANG_COLORS = {
    "Java": "#b07219", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "Python": "#3572A5", "HTML": "#e34c26", "CSS": "#663399", "Vue": "#41b883",
    "Assembly": "#6E4C13", "SCSS": "#c6538c", "Shell": "#89e051",
    "PHP": "#4F5D95", "C": "#555555", "C++": "#f34b7d", "Dockerfile": "#384d54",
}

# 5x7 pixel font for the banner name.
GLYPHS = {
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".####", "#....", "#....", "#....", "#....", "#....", ".####"],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "G": [".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"],
    "J": ["..###", "....#", "....#", "....#", "....#", "#...#", ".###."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    " ": ["....."] * 7,
}


def load(name):
    return json.loads((ASSETS / name).read_text(encoding="utf-8"))


def write(name, svg):
    (ASSETS / name).write_text(svg, encoding="utf-8")
    print(f"  wrote assets/{name}")


def esc(s):
    return escape(str(s), {'"': "&quot;"})


# --------------------------------------------------------------------------- banner

def pixel_text(lines, x0, y0, cell, t):
    """Pixel-art name with a left-to-right reveal and a slow colour cycle."""
    out = []
    for li, word in enumerate(lines):
        y_base = y0 + li * (7 * cell + cell * 2)
        col_offset = 0
        for ch in word.upper():
            glyph = GLYPHS.get(ch, GLYPHS[" "])
            for r, row in enumerate(glyph):
                for c, px in enumerate(row):
                    if px != "#":
                        continue
                    col = col_offset + c
                    x = x0 + col * cell
                    y = y_base + r * cell
                    delay = 0.25 + li * 0.35 + col * 0.025
                    out.append(
                        f'<rect x="{x}" y="{y}" width="{cell - 1}" height="{cell - 1}" rx="1" '
                        f'fill="url(#nameGrad)" opacity="0">'
                        f'<animate attributeName="opacity" from="0" to="1" begin="{delay:.2f}s" '
                        f'dur="0.25s" fill="freeze"/></rect>'
                    )
            col_offset += 6
    return "\n".join(out)


def banner(profile, mode):
    t = THEMES[mode]
    W, H = 1200, 560
    dark = mode == "dark"
    glow = 0.28 if dark else 0.10

    # left panel geometry
    LX, LY, LW, LH = 24, 68, 452, 468
    RX, RY, RW, RH = 492, 68, 684, 468

    lines = profile["name_lines"]
    longest = max(len(w) for w in lines)
    cell = min(12, (LW - 60) // (longest * 6))
    name_w = longest * 6 * cell - cell
    name_x = LX + (LW - name_w) // 2
    name_y = LY + 70

    after_name = name_y + len(lines) * (9 * cell) + 10

    info_rows = []
    for i, (k, v) in enumerate(profile["info"]):
        y = RY + 76 + i * 27
        d = 0.9 + i * 0.12
        info_rows.append(
            f'<g opacity="0" transform="translate(-8 0)">'
            f'<animate attributeName="opacity" from="0" to="1" begin="{d:.2f}s" dur="0.35s" fill="freeze"/>'
            f'<animateTransform attributeName="transform" type="translate" from="-8 0" to="0 0" '
            f'begin="{d:.2f}s" dur="0.35s" fill="freeze"/>'
            f'<text x="{RX + 28}" y="{y}" fill="{t["pink"]}">›</text>'
            f'<text x="{RX + 48}" y="{y}" fill="{t["purple"]}" font-weight="700">{esc(k)}</text>'
            f'<text x="{RX + 200}" y="{y}" fill="{t["muted"]}">::</text>'
            f'<text x="{RX + 226}" y="{y}" fill="{t["fg"]}">{esc(v)}</text>'
            f"</g>"
        )

    j = profile["journey"]
    bar_x, bar_y, bar_w = LX + 36, after_name + 78, LW - 72
    bar_fill = bar_w * j["percent"] / 100

    prompt_y = RY + RH - 34
    prompt_user = "xanthus@co:~$"
    prompt_x = RX + 28
    cmd_x = prompt_x + int(len(prompt_user) * 8.6) + 12
    cmd = profile["prompt"]
    cmd_w = int(len(cmd) * 8.6) + 4
    type_begin = 0.9 + len(profile["info"]) * 0.12 + 0.4

    return f"""<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="{MONO}" role="img" aria-label="{esc(profile['full_name'])} — profile.sh --live">
<title>{esc(profile['full_name'])} — live terminal profile</title>
<defs>
  <clipPath id="card"><rect width="{W}" height="{H}" rx="22"/></clipPath>
  <clipPath id="leftClip"><rect x="{LX}" y="{LY}" width="{LW}" height="{LH}" rx="16"/></clipPath>
  <clipPath id="typeClip"><rect x="{cmd_x}" y="{prompt_y - 16}" width="0" height="24">
    <animate attributeName="width" from="0" to="{cmd_w}" begin="{type_begin:.2f}s" dur="{len(cmd) * 0.06:.2f}s" fill="freeze"/>
  </rect></clipPath>
  <pattern id="grid" width="22" height="22" patternUnits="userSpaceOnUse">
    <path d="M22 0H0V22" fill="none" stroke="{t['grid']}" stroke-width="1"/>
  </pattern>
  <radialGradient id="glowA"><stop offset="0" stop-color="{t['purple']}" stop-opacity="{glow}"/><stop offset="1" stop-color="{t['purple']}" stop-opacity="0"/></radialGradient>
  <radialGradient id="glowB"><stop offset="0" stop-color="{t['pink']}" stop-opacity="{glow * 0.8:.2f}"/><stop offset="1" stop-color="{t['pink']}" stop-opacity="0"/></radialGradient>
  <radialGradient id="glowC"><stop offset="0" stop-color="{t['cyan']}" stop-opacity="{glow * 0.7:.2f}"/><stop offset="1" stop-color="{t['cyan']}" stop-opacity="0"/></radialGradient>
  <linearGradient id="nameGrad" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{t['purple']}"><animate attributeName="stop-color" values="{t['purple']};{t['pink']};{t['cyan']};{t['purple']}" dur="8s" repeatCount="indefinite"/></stop>
    <stop offset="1" stop-color="{t['pink']}"><animate attributeName="stop-color" values="{t['pink']};{t['cyan']};{t['purple']};{t['pink']}" dur="8s" repeatCount="indefinite"/></stop>
  </linearGradient>
  <linearGradient id="barGrad" x1="0" x2="1"><stop offset="0" stop-color="{t['purple']}"/><stop offset="1" stop-color="{t['pink']}"/></linearGradient>
  <linearGradient id="scan" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{t['purple']}" stop-opacity="0"/><stop offset="0.5" stop-color="{t['purple']}" stop-opacity="{0.16 if dark else 0.08}"/><stop offset="1" stop-color="{t['purple']}" stop-opacity="0"/></linearGradient>
</defs>

<g clip-path="url(#card)">
  <rect width="{W}" height="{H}" fill="{t['bg']}"/>
  <circle cx="140" cy="120" r="260" fill="url(#glowA)"/>
  <circle cx="1080" cy="470" r="280" fill="url(#glowB)"/>
  <circle cx="640" cy="40" r="200" fill="url(#glowC)"/>

  <!-- title bar -->
  <rect width="{W}" height="48" fill="{t['panel']}"/>
  <line x1="0" y1="48" x2="{W}" y2="48" stroke="{t['border']}"/>
  <circle cx="30" cy="24" r="6.5" fill="{t['red']}"/>
  <circle cx="52" cy="24" r="6.5" fill="{t['yellow'] if dark else t['orange']}"/>
  <circle cx="74" cy="24" r="6.5" fill="{t['green']}"/>
  <text x="{W // 2}" y="29" text-anchor="middle" font-size="14" fill="{t['muted']}">xanthus@colombia: <tspan fill="{t['fg']}">~/profile.sh --live</tspan></text>
  <rect x="{W - 96}" y="13" width="72" height="22" rx="11" fill="none" stroke="{t['green']}" stroke-opacity="0.6"/>
  <circle cx="{W - 80}" cy="24" r="4" fill="{t['green']}"><animate attributeName="opacity" values="1;0.2;1" dur="1.6s" repeatCount="indefinite"/></circle>
  <text x="{W - 68}" y="28.5" font-size="12" font-weight="700" fill="{t['green']}">LIVE</text>

  <!-- left panel: VISUAL.MAP -->
  <rect x="{LX}" y="{LY}" width="{LW}" height="{LH}" rx="16" fill="{t['panel']}" stroke="{t['border']}"/>
  <g clip-path="url(#leftClip)">
    <rect x="{LX}" y="{LY}" width="{LW}" height="{LH}" fill="url(#grid)" opacity="0.7"/>
    <rect x="{LX}" y="{LY - 120}" width="{LW}" height="120" fill="url(#scan)">
      <animate attributeName="y" from="{LY - 120}" to="{LY + LH}" dur="4.5s" repeatCount="indefinite"/>
    </rect>
  </g>
  <text x="{LX + 20}" y="{LY + 30}" font-size="12" fill="{t['muted']}" letter-spacing="2">VISUAL.MAP</text>
  <text x="{LX + LW - 20}" y="{LY + 30}" text-anchor="end" font-size="12" fill="{t['muted']}">5×7 / PIXEL</text>
{pixel_text(lines, name_x, name_y, cell, t)}
  <text x="{LX + LW // 2}" y="{after_name + 12}" text-anchor="middle" font-size="16" font-weight="700" fill="{t['pink']}">@{esc(profile['user'])}</text>
  <text x="{LX + LW // 2}" y="{after_name + 38}" text-anchor="middle" font-size="13" fill="{t['fg']}">{esc(profile['tagline'])}</text>

  <text x="{bar_x}" y="{bar_y - 10}" font-size="12" fill="{t['muted']}">{esc(j['label'])}</text>
  <text x="{bar_x + bar_w}" y="{bar_y - 10}" text-anchor="end" font-size="12" fill="{t['fg']}">{j['percent']}%</text>
  <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="10" rx="5" fill="{t['border']}" opacity="0.6"/>
  <rect x="{bar_x}" y="{bar_y}" width="0" height="10" rx="5" fill="url(#barGrad)">
    <animate attributeName="width" from="0" to="{bar_fill:.1f}" begin="1.2s" dur="1.6s" calcMode="spline" keyTimes="0;1" keySplines="0.22 1 0.36 1" fill="freeze"/>
  </rect>

  <circle cx="{LX + 30}" cy="{LY + LH - 30}" r="5" fill="{t['green']}"><animate attributeName="opacity" values="1;0.3;1" dur="2s" repeatCount="indefinite"/></circle>
  <text x="{LX + 44}" y="{LY + LH - 25.5}" font-size="13" font-weight="700" fill="{t['green']}">ALL SYSTEMS NOMINAL</text>
  <text x="{LX + LW - 20}" y="{LY + LH - 25.5}" text-anchor="end" font-size="12" fill="{t['muted']}">CO · LATAM NODE</text>

  <!-- right panel: SYSTEM.INFO -->
  <rect x="{RX}" y="{RY}" width="{RW}" height="{RH}" rx="16" fill="{t['panel']}" stroke="{t['border']}"/>
  <text x="{RX + 28}" y="{RY + 30}" font-size="12" fill="{t['muted']}" letter-spacing="2">SYSTEM.INFO</text>
  <text x="{RX + RW - 24}" y="{RY + 30}" text-anchor="end" font-size="12" fill="{t['muted']}">{esc(profile['full_name'])}'s live system profile</text>
  <line x1="{RX + 24}" y1="{RY + 44}" x2="{RX + RW - 24}" y2="{RY + 44}" stroke="{t['border']}"/>
  <g font-size="14">
{chr(10).join(info_rows)}
  </g>
  <line x1="{RX + 24}" y1="{prompt_y - 32}" x2="{RX + RW - 24}" y2="{prompt_y - 32}" stroke="{t['border']}"/>
  <text x="{prompt_x}" y="{prompt_y}" font-size="14" font-weight="700" fill="{t['green']}">{prompt_user}</text>
  <text x="{cmd_x}" y="{prompt_y}" font-size="14" fill="{t['cyan']}" clip-path="url(#typeClip)">{esc(cmd)}</text>
  <rect x="{cmd_x}" y="{prompt_y - 14}" width="9" height="18" fill="{t['fg']}">
    <animate attributeName="x" from="{cmd_x}" to="{cmd_x + cmd_w}" begin="{type_begin:.2f}s" dur="{len(cmd) * 0.06:.2f}s" fill="freeze"/>
    <animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.5;1" dur="1s" repeatCount="indefinite"/>
  </rect>
</g>
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="22" fill="none" stroke="{t['border']}"/>
</svg>
"""


# --------------------------------------------------------------------------- radar

def radar(data, mode, fill_key, stroke_key):
    t = THEMES[mode]
    axes = data["axes"]
    n = len(axes)
    W, H, R = 600, 500, 160
    cx, cy = W / 2, 262

    def pt(i, r):
        a = -math.pi / 2 + 2 * math.pi * i / n
        return r * math.cos(a), r * math.sin(a)

    rings = []
    for k in (1.0, 0.75, 0.5, 0.25):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, R * k) for i in range(n)))
        rings.append(f'<polygon points="{pts}" fill="none" stroke="{t["border"]}" opacity="{0.4 + k * 0.5:.2f}"/>')
    spokes = [
        f'<line x1="0" y1="0" x2="{x:.1f}" y2="{y:.1f}" stroke="{t["border"]}" opacity="0.6"/>'
        for x, y in (pt(i, R) for i in range(n))
    ]
    vals = [pt(i, R * v / 100) for i, (_, v) in enumerate(axes)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in vals)
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{t[stroke_key]}" stroke="{t["bg"]}" stroke-width="1.5"/>'
        for x, y in vals
    )

    labels = []
    for i, (name, v) in enumerate(axes):
        x, y = pt(i, R + 26)
        anchor = "middle" if abs(x) < 20 else ("start" if x > 0 else "end")
        dy = -6 if y < -R * 0.8 else (14 if y > R * 0.8 else 4)
        labels.append(
            f'<text x="{x:.1f}" y="{y + dy:.1f}" text-anchor="{anchor}" font-size="13" font-weight="600" fill="{t["fg"]}">{esc(name)}</text>'
            f'<text x="{x:.1f}" y="{y + dy + 16:.1f}" text-anchor="{anchor}" font-size="11.5" fill="{t["muted"]}">{v}</text>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{esc(data['title'])}" font-family="{SANS}">
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="{t['bg']}" stroke="{t['border']}"/>
<text x="{W / 2}" y="34" text-anchor="middle" font-size="16" font-weight="700" fill="{t['purple']}">{esc(data['title'])}</text>
<g transform="translate({cx},{cy})">
{''.join(rings)}{''.join(spokes)}
<g><animateTransform attributeName="transform" type="scale" values="0.04;1" dur="1.1s" calcMode="spline" keyTimes="0;1" keySplines="0.22 1 0.36 1" fill="freeze"/>
<polygon points="{poly}" fill="{t[fill_key]}" fill-opacity="0.25" stroke="{t[stroke_key]}" stroke-width="2.5" stroke-linejoin="round"/>{dots}
</g>
{''.join(labels)}
</g>
</svg>
"""


# --------------------------------------------------------------------------- GitHub data

def token():
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def api(url, body=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-generator"}
    if token():
        headers["Authorization"] = f"Bearer {token()}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fetch(user):
    info = api(f"https://api.github.com/users/{user}")
    repos = api(f"https://api.github.com/users/{user}/repos?per_page=100&type=owner")
    own = [r for r in repos if not r["fork"]]
    langs = {}
    for r in own:
        for lang, b in api(r["languages_url"]).items():
            langs[lang] = langs.get(lang, 0) + b

    stats = {
        "stars": sum(r["stargazers_count"] for r in own),
        "repos": info["public_repos"],
        "followers": info["followers"],
        "contrib": None, "streak": None, "longest": None,
    }
    if token():
        q = """query($u:String!){user(login:$u){contributionsCollection{contributionCalendar{
               totalContributions weeks{contributionDays{date contributionCount}}}}}}"""
        cal = api("https://api.github.com/graphql", {"query": q, "variables": {"u": user}})
        cal = cal["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        days = [d["contributionCount"] for w in cal["weeks"] for d in w["contributionDays"]]
        longest = run = 0
        for c in days:
            run = run + 1 if c else 0
            longest = max(longest, run)
        cur = 0
        # today may still be empty: don't break the streak for it
        for i, c in enumerate(reversed(days)):
            if c:
                cur += 1
            elif i > 0:
                break
        stats.update(contrib=cal["totalContributions"], streak=cur, longest=longest)
    return stats, langs, {r["name"]: r for r in own}


def stats_card(user, s, mode):
    t = THEMES[mode]
    fmt = lambda v: "—" if v is None else f"{v:,}"
    cells = [
        ("Total stars", s["stars"], "purple"), ("Public repos", s["repos"], "pink"),
        ("Followers", s["followers"], "cyan"), ("Contributions (1y)", s["contrib"], "green"),
        ("Current streak", s["streak"], "orange"), ("Longest streak", s["longest"], "yellow"),
    ]
    body = []
    for i, (label, v, c) in enumerate(cells):
        x = 24 + (i % 3) * 150
        y = 82 + (i // 3) * 50
        body.append(
            f'<rect x="{x - 10}" y="{y - 20}" width="3" height="34" rx="1.5" fill="{t[c]}"/>'
            f'<text x="{x}" y="{y}" font-size="23" font-weight="700" fill="{t["fg"]}">{fmt(v)}</text>'
            f'<text x="{x}" y="{y + 17}" font-size="11" fill="{t["muted"]}">{label}</text>'
        )
    stamp = dt.date.today().isoformat()
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 170" width="480" height="170" role="img" aria-label="{user} GitHub statistics" font-family="{SANS}">
<rect x="0.5" y="0.5" width="479" height="169" rx="12" fill="{t['bg']}" stroke="{t['border']}"/>
<text x="24" y="34" font-size="15" font-weight="700" fill="{t['purple']}">@{user}</text>
<text x="456" y="34" font-size="11" text-anchor="end" fill="{t['muted']}">at a glance · {stamp}</text>
<line x1="24" y1="46" x2="456" y2="46" stroke="{t['border']}"/>
{''.join(body)}
</svg>
"""


def langs_card(langs, mode):
    t = THEMES[mode]
    total = sum(langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1])[:6]
    top_total = sum(b for _, b in top) or 1
    bar, legend, x = [], [], 24.0
    for i, (lang, b) in enumerate(top):
        w = 432 * b / top_total
        color = LANG_COLORS.get(lang, t["muted"])
        bar.append(f'<rect x="{x:.1f}" y="58" width="{w:.1f}" height="10" fill="{color}"/>')
        x += w
        lx, ly = 24 + (i % 2) * 216, 96 + (i // 2) * 24
        legend.append(
            f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{color}"/>'
            f'<text x="{lx + 16}" y="{ly}" font-size="12.5" fill="{t["fg"]}">{esc(lang)}</text>'
            f'<text x="{lx + 190}" y="{ly}" text-anchor="end" font-size="12" fill="{t["muted"]}">{100 * b / total:.1f}%</text>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 170" width="480" height="170" role="img" aria-label="Most used languages" font-family="{SANS}">
<rect x="0.5" y="0.5" width="479" height="169" rx="12" fill="{t['bg']}" stroke="{t['border']}"/>
<text x="24" y="34" font-size="15" font-weight="700" fill="{t['purple']}">Most used languages</text>
<text x="456" y="34" font-size="11" text-anchor="end" fill="{t['muted']}">by bytes · own repos</text>
<clipPath id="barClip"><rect x="24" y="58" width="432" height="10" rx="5"/></clipPath>
<g clip-path="url(#barClip)">{''.join(bar)}</g>
{''.join(legend)}
</svg>
"""


def wrap(text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + [cur] if cur else lines


def project_card(p, repo, mode):
    t = THEMES[mode]
    desc = p.get("description") or (repo or {}).get("description") or ""
    lang = (repo or {}).get("language") or "—"
    stars = (repo or {}).get("stargazers_count", 0)
    updated = ((repo or {}).get("pushed_at") or "")[:10]
    color = LANG_COLORS.get(lang, t["muted"])
    desc_lines = "".join(
        f'<text x="24" y="{66 + i * 19}" font-size="13" fill="{t["fg"]}">{esc(l)}</text>'
        for i, l in enumerate(wrap(desc, 50)[:2])
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 140" width="420" height="140" role="img" aria-label="{esc(p['repo'])}" font-family="{SANS}">
<rect x="0.5" y="0.5" width="419" height="139" rx="12" fill="{t['bg']}" stroke="{t['border']}"/>
<rect x="0.5" y="16" width="3" height="30" rx="1.5" fill="{t['pink']}"/>
<text x="24" y="37" font-size="16" font-weight="700" fill="{t['purple']}">{esc(p['repo'])}</text>
<text x="396" y="37" text-anchor="end" font-size="11" fill="{t['muted']}">{updated}</text>
{desc_lines}
<circle cx="30" cy="115" r="5.5" fill="{color}"/>
<text x="42" y="119.5" font-size="12" fill="{t['muted']}">{esc(lang)}</text>
<text x="396" y="119.5" text-anchor="end" font-size="12" fill="{t['muted']}">★ {stars}</text>
</svg>
"""


# --------------------------------------------------------------------------- main

def main():
    profile = load("profile.json")
    skills, langmix, projects = load("skills.json"), load("langmix.json"), load("projects.json")

    for mode in ("dark", "light"):
        write(f"banner-{mode}.svg", banner(profile, mode))
        write(f"radar-{mode}.svg", radar(skills, mode, "purple", "pink"))
        write(f"radar-langs-{mode}.svg", radar(langmix, mode, "cyan", "green"))

    try:
        stats, langs, repos = fetch(profile["user"])
    except Exception as e:  # keep the last good cards
        print(f"  ! GitHub API unavailable ({e}); stats/project cards left untouched", file=sys.stderr)
        return
    for mode in ("dark", "light"):
        write(f"card-stats-{mode}.svg", stats_card(profile["user"], stats, mode))
        write(f"card-langs-{mode}.svg", langs_card(langs, mode))
        for p in projects:
            write(f"card-{p['repo']}-{mode}.svg", project_card(p, repos.get(p["repo"]), mode))


if __name__ == "__main__":
    main()
