import base64

import markdown

# 针对代码块的样式：浅灰背景、等宽字体、圆角
CODE_BLOCK_CSS = """
<style>
  pre {
    background-color: #f5f5f5;
    color: #24292e;
    padding: 12px;
    border-radius: 6px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 13px;
    border: 1px solid #e1e4e8;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
  code {
    background-color: #f0f0f0;
    color: #c7254e;
    padding: 2px 5px;
    border-radius: 3px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 13px;
  }
  pre code {
    background: transparent;
    color: inherit;
    padding: 0;
  }
  blockquote {
    border-left: 4px solid #ddd;
    margin: 8px 0;
    padding-left: 12px;
    color: #666;
  }
  table {
    border-collapse: collapse;
    margin: 8px 0;
  }
  th, td {
    border: 1px solid #ddd;
    padding: 6px 10px;
  }
  th {
    background-color: #f2f2f2;
  }
</style>
"""


def _unhtml_escape(text: str) -> str:
    """反转义 HTML 实体。注意：&amp; 必须先处理，否则 &amp;lt; 会被错误还原成 <。"""
    return (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&#39;", "'")
    )


def _make_copy_anchor(code_text: str) -> str:
    """将代码文本编码为 copy:// 锚点，供 QTextBrowser 点击复制。"""
    encoded = base64.b64encode(code_text.encode("utf-8")).decode("ascii")
    return f'<a href="copy://{encoded}" style="color:#0366d6;">📋 复制</a>'


def _inject_copy_anchors(html: str) -> str:
    """在每个 </code></pre> 之后插入复制锚点。"""
    result_parts: list[str] = []
    remaining = html
    close_tag = "</code></pre>"
    while close_tag in remaining:
        idx = remaining.find(close_tag)
        code_open = remaining.rfind("<code>", 0, idx)
        if code_open == -1:
            result_parts.append(remaining[: idx + len(close_tag)])
            remaining = remaining[idx + len(close_tag) :]
            continue
        code_text = remaining[code_open + len("<code>") : idx]
        code_text = _unhtml_escape(code_text)
        anchor = _make_copy_anchor(code_text)
        result_parts.append(remaining[: idx + len(close_tag)] + f"<p>{anchor}</p>")
        remaining = remaining[idx + len(close_tag) :]

    result_parts.append(remaining)
    return "".join(result_parts)


def render_markdown_body(markdown_text: str) -> str:
    """将 Markdown 渲染为 body 片段（不含 <html> 外壳与 CSS）。"""
    html = markdown.markdown(
        markdown_text,
        extensions=["fenced_code", "tables", "nl2br"],
    )
    return _inject_copy_anchors(html)


def render_markdown_to_html(markdown_text: str) -> str:
    """将 Markdown 文本渲染为带样式的完整 HTML。"""
    body = render_markdown_body(markdown_text)
    styled = CODE_BLOCK_CSS + body
    return f'<html><head><meta charset="utf-8"></head>' f"<body>{styled}</body></html>"


def decode_copy_url(url: str) -> str | None:
    """从 copy:// 锚点中解出原始代码文本。非 copy 协议返回 None。"""
    if not url.startswith("copy://"):
        return None
    b64 = url[len("copy://") :]
    try:
        return base64.b64decode(b64).decode("utf-8")
    except Exception:
        return None
