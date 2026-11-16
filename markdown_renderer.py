import base64
import re

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
    """将代码文本编码为 #copy: 锚点，供 QTextBrowser 点击复制。

    说明：
      - 使用 fragment (#) 形式而非 copy://xxx：QTextBrowser 对找不到的 fragment
        不会触发 scrollToAnchor 回退，从而保持滚动位置不跳顶。
      - 使用 urlsafe base64（- 和 _ 替代 + /）并去掉尾部 =：避免 QUrl 对
        base64 中的 + / = 做规范化，导致解码失败。
    """
    encoded = (
        base64.urlsafe_b64encode(code_text.encode("utf-8")).decode("ascii").rstrip("=")
    )
    return f'<a href="#copy:{encoded}" style="color:#0366d6;">📋 复制</a>'


# 精确匹配 markdown 的 fenced_code 生成的块级代码结构：
#   <pre><code class="language-xxx">...</code></pre>
# 使用 [^>]* 兼容可能出现的 class 属性；
# 使用 .*? 非贪婪，代码块内若被转义过的字面 </code></pre> 不参与匹配。
_CODE_BLOCK_RE = re.compile(
    r"<pre><code[^>]*>(?P<code>.*?)</code></pre>",
    re.DOTALL,
)


def _inject_copy_anchors(html: str) -> str:
    """在每个 <pre><code>...</code></pre> 之后插入复制锚点。

    旧实现使用 ``rfind("<code>")`` 定位代码起点，在当前 HTML 里前面出现
    行内代码（如标题中的 `xxx`）时，会错误地把行内 <code> 当作块级代码
    起点，导致复制内容混入前置 HTML 片段（例如 "</code>）</h3>"）。
    改用正则整段匹配 <pre><code>...</code></pre>，边界只来自完整代码块。
    """

    def _replace(match: "re.Match[str]") -> str:
        code_text = _unhtml_escape(match.group("code"))
        anchor = _make_copy_anchor(code_text)
        return f"{match.group(0)}<p>{anchor}</p>"

    return _CODE_BLOCK_RE.sub(_replace, html)


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
    """从 #copy: 锚点解出原始代码文本。非 copy 协议返回 None。

    兼容旧 copy:// 格式以防缓存/历史脏数据，但优先使用 #copy: 格式。
    """
    payload = None
    if url.startswith("#copy:"):
        payload = url[len("#copy:") :]
    elif url.startswith("copy://"):
        # 兼容旧格式（若某些环境下仍有残留）
        payload = url[len("copy://") :]
    if payload is None:
        return None

    # urlsafe base64 兼容处理（补 = 到 4 的倍数）
    padding = (-len(payload)) % 4
    try:
        return base64.urlsafe_b64decode(payload + ("=" * padding)).decode("utf-8")
    except Exception:
        return None
