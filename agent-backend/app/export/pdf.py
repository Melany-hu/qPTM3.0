"""Export assistant markdown answers to a compact, sharp, styled PDF."""

from __future__ import annotations

import base64
import html as html_lib
import logging
import re
from pathlib import Path

import markdown

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_LOGO_PATH = _PROJECT_ROOT / "assets" / "img" / "logo.png"
_FONT_PATH = Path("/usr/share/fonts/google-droid/DroidSansFallback.ttf")

_EMOJI_REPLACEMENTS = {
    "⚠️": "[!]",
    "⚠": "[!]",
    "✅": "[OK]",
    "❌": "[X]",
    "✔": "[OK]",
    "✗": "[X]",
    "•": "-",
    "·": "-",
    "→": "->",
    "←": "<-",
    "⇒": "=>",
    "≥": ">=",
    "≤": "<=",
    "×": "x",
    "\ufe0f": "",
}


def _normalize_markdown(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    for src, dst in _EMOJI_REPLACEMENTS.items():
        text = text.replace(src, dst)
    # Drop raw ">" before callouts that already have icons/text.
    text = re.sub(r"(?m)^>\s?", "", text)
    return text


def _markdown_to_html(md_text: str) -> str:
    html = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
        output_format="html",
    )
    html = re.sub(r"<p>\s*&gt;\s*", "<p>", html)
    return html


def _logo_data_uri() -> str:
    if not _LOGO_PATH.is_file():
        return ""
    raw = _LOGO_PATH.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _build_document_html(body_html: str) -> str:
    logo_uri = _logo_data_uri()
    font_url = _FONT_PATH.as_uri() if _FONT_PATH.is_file() else ""
    watermark = (
        f'<img class="watermark" src="{html_lib.escape(logo_uri, quote=True)}" alt="">'
        if logo_uri
        else ""
    )
    font_face = ""
    if font_url:
        font_face = f"""
        @font-face {{
          font-family: 'qptm-cjk';
          src: url('{font_url}');
          font-weight: normal;
          font-style: normal;
        }}
        """

    # Visual language mirrors agent.php .msg-content + the earlier html2canvas export
    # (blue page wash, primary headings/tables, soft callouts, centered logo).
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
{font_face}
@page {{
  size: A4;
  margin: 16mm 15mm 16mm 15mm;
  background: linear-gradient(180deg, #e0edff 0%, #eef5ff 55%, #f5f7fa 100%);
  @bottom-center {{
    content: counter(page) " / " counter(pages);
    font-family: 'qptm-cjk', sans-serif;
    font-size: 9pt;
    color: #8c919b;
  }}
}}
html, body {{
  margin: 0;
  padding: 0;
  color: #1a1a2e;
  font-family: 'qptm-cjk', "Noto Sans CJK SC", "Source Han Sans SC", sans-serif;
  font-size: 10.5pt;
  line-height: 1.65;
}}
.page {{
  position: relative;
}}
.watermark {{
  position: fixed;
  top: 50%;
  left: 50%;
  width: 42%;
  max-width: 280px;
  opacity: 0.14;
  transform: translate(-50%, -50%);
  z-index: 0;
}}
.card {{
  position: relative;
  z-index: 1;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid #d7e3f4;
  border-radius: 12px;
  padding: 16px 18px;
}}
h1, h2, h3, h4, h5, h6 {{
  color: #0e74d3;
  font-weight: 700;
  line-height: 1.35;
  margin: 1.05em 0 0.4em;
  page-break-after: avoid;
}}
h1 {{ font-size: 1.3em; }}
h2 {{ font-size: 1.15em; }}
h3 {{ font-size: 1.05em; font-weight: 600; }}
h4 {{ font-size: 1em; font-weight: 600; }}
h5 {{ font-size: 0.95em; font-weight: 600; color: #0a5fad; }}
h6 {{ font-size: 0.9em; font-weight: 600; color: #6b7280; }}
p {{ margin: 0 0 0.65em; }}
p:last-child {{ margin-bottom: 0; }}
strong {{ font-weight: 700; }}
em {{ font-style: italic; }}
a {{ color: #0e74d3; text-decoration: none; }}
ul, ol {{
  margin: 0.35em 0 0.7em 1.35em;
  padding: 0;
}}
li {{ margin: 0.2em 0; }}
hr {{
  border: none;
  border-top: 1px solid #d7e3f4;
  margin: 1em 0;
}}
blockquote {{
  margin: 0.75em 0;
  padding: 0.7em 0.95em;
  border-left: 3px solid #9dc4ef;
  background: rgba(232, 242, 255, 0.55);
  border-radius: 0 8px 8px 0;
  color: #1a1a2e;
}}
blockquote p {{ margin: 0 0 0.35em; }}
blockquote p:last-child {{ margin-bottom: 0; }}
code {{
  background: #e0edff;
  padding: 0.08em 0.32em;
  border-radius: 3px;
  font-size: 0.88em;
}}
pre {{
  background: #f5f7fa;
  border: 1px solid #d7e3f4;
  border-radius: 10px;
  padding: 0.8em 0.95em;
  word-wrap: break-word;
  white-space: pre-wrap;
  margin: 0.65em 0;
  font-size: 0.9em;
}}
pre code {{
  background: none;
  padding: 0;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  margin: 0.75em 0 1em;
  font-size: 0.86em;
  line-height: 1.45;
  table-layout: fixed;
  word-wrap: break-word;
}}
thead {{ display: table-header-group; }}
tr {{ page-break-inside: avoid; }}
th, td {{
  border: 1px solid #c9daf0;
  padding: 0.42em 0.55em;
  text-align: left;
  vertical-align: top;
  word-wrap: break-word;
}}
th {{
  background: #e0edff;
  color: #0e74d3;
  font-weight: 700;
}}
tr:nth-child(even) td {{
  background: #f5f7fa;
}}
</style>
</head>
<body>
  <div class="page">
    {watermark}
    <div class="card">
      {body_html}
    </div>
  </div>
</body>
</html>
"""


def build_answer_pdf(markdown_text: str) -> bytes:
    """Render markdown to a styled PDF matching the agent page look."""
    try:
        from weasyprint import HTML
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"WeasyPrint is unavailable: {exc}") from exc

    if not _FONT_PATH.is_file():
        raise RuntimeError(f"CJK font not found: {_FONT_PATH}")

    md_text = _normalize_markdown(markdown_text) or "(Empty answer)"
    body_html = _markdown_to_html(md_text)
    document = _build_document_html(body_html)
    return HTML(string=document, base_url=str(_PROJECT_ROOT)).write_pdf()
