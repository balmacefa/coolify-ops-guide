"""Build the static site: docs/*.md -> site/docs/*.html, plus a docs index."""
import html
import re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = ROOT / "site" / "docs"

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · Coolify Ops Guide</title>
<link rel="stylesheet" href="{base}style.css"></head>
<body><header><a href="{base}index.html">Coolify Ops Guide</a>
<nav><a href="{base}docs/index.html">Docs</a>
<a href="https://github.com/balmacefa/coolify-ops-guide">GitHub</a></nav></header>
<main>{body}</main>
<footer>MIT · unofficial community guide, not affiliated with Coolify.</footer>
</body></html>"""


def title_of(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else fallback


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    entries = []
    for md in sorted(DOCS.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        title = title_of(text, md.stem)
        body = markdown.markdown(text, extensions=["fenced_code", "tables", "toc"])
        body = re.sub(r'href="([^"]+)\.md(#[^"]*)?"', r'href="\1.html\2"', body)
        (OUT / f"{md.stem}.html").write_text(
            PAGE.format(title=html.escape(title), base="../", body=body), encoding="utf-8")
        entries.append((md.stem, title))
    items = "\n".join(f'<li><a href="{s}.html">{html.escape(t)}</a></li>' for s, t in entries)
    (OUT / "index.html").write_text(
        PAGE.format(title="Docs", base="../", body=f"<h1>Docs</h1><ul>{items}</ul>"),
        encoding="utf-8")
    print(f"built {len(entries)} pages")


if __name__ == "__main__":
    main()
