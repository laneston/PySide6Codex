# DeepSeek 桌面客户端

一个基于 **PySide6** 的 DeepSeek 桌面聊天客户端，支持多会话管理、Markdown 渲染、代码块一键复制、文本/图片附件分析以及流式输出。

---

## 一、功能特性

| 功能          | 说明                                                               |
| ------------- | ------------------------------------------------------------------ |
| 多会话管理    | 启动时选择历史会话，或新建对话；支持删除、切换、清空               |
| 流式输出      | 通过后台线程调用 DeepSeek API，逐字流式显示回复，不阻塞界面        |
| Markdown 渲染 | 回复内容按 Markdown 渲染，支持表格、引用、代码块高亮样式           |
| 代码块复制    | 每个代码块下方自动生成「📋 复制」锚点，点击即复制纯代码文本         |
| 附件分析      | 支持上传代码/文本文件（自动拼接进 prompt）与图片（多模态模型分析） |
| 图片历史裁剪  | 仅最近 3 条消息内的图片会发送给模型，避免请求超长/超限             |
| 本地持久化    | 会话元数据、消息、图片全部保存在本地磁盘，重启可恢复               |
| 纯文本粘贴    | 粘贴时自动去除富文本格式，保留换行与空格                           |
| 上下文保护    | 生成过程中禁用切换/清空/发送等按钮，避免状态错乱                   |

---

## 二、项目结构

```
.
├── pySide6Codex.py        # 程序入口，AppController 负责会话选择与主窗口切换
├── session_selector.py    # 启动时的「选择/新建/删除会话」对话框
├── main_window.py         # 主窗口：聊天视图、附件、发送、流式显示、清空
├── api_worker.py          # StreamWorker：后台线程调用 DeepSeek 流式接口
├── chat_store.py          # 本地存储：会话目录、元数据、消息、图片的读写
├── chat_widgets.py        # MarkdownChatView（Markdown 渲染视图）、PlainPasteTextEdit
├── markdown_renderer.py   # Markdown → HTML 渲染 + 代码块复制锚点注入
└── README.md
```

---

## 三、环境要求

- **Python**：3.10 及以上（使用了 `str | None`、`list[dict]` 等类型语法）
- **操作系统**：Windows / macOS / Linux（PySide6 跨平台）
- **网络**：可访问 `https://api.deepseek.com`
- **DeepSeek API Key**：需在 [DeepSeek 开放平台](https://platform.deepseek.com/) 申请

### 依赖包

| 包名            | 用途                                 |
| --------------- | ------------------------------------ |
| `PySide6`       | GUI 框架                             |
| `openai`        | 调用 DeepSeek 兼容 OpenAI 协议的接口 |
| `python-dotenv` | 从 `.env` 文件加载 API Key           |
| `markdown`      | Markdown 渲染为 HTML                 |

---

## 四、部署步骤

### 1. 获取源码

将上述所有 `.py` 文件放到同一个项目目录中，例如：

```
deepseek-desktop/
├── pySide6Codex.py
├── session_selector.py
├── main_window.py
├── api_worker.py
├── chat_store.py
├── chat_widgets.py
├── markdown_renderer.py
└── .env              # 稍后创建
```

### 2. 创建虚拟环境（推荐）

**Windows：**

```bash
python -m venv .venv
.venv\Scripts\activate
```

**macOS / Linux：**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 安装依赖

在项目根目录创建 `requirements.txt`：

```txt
PySide6>=6.5
openai>=1.0
python-dotenv>=1.0
markdown>=3.5
```

然后执行：

```bash
pip install -r requirements.txt
```

> 如在国内网络较慢，可使用镜像源：
> `pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

### 4. 配置 API Key

在项目根目录创建 `.env` 文件，内容如下：

```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

> ⚠️ 未设置该变量时，程序启动会打印错误并直接退出。
> `.env` 文件包含密钥，**不要提交到 Git 仓库**，建议加入 `.gitignore`。

### 5. 运行程序

```bash
python pySide6Codex.py
```

程序将首先弹出「选择对话」窗口。

---

## 五、可选：打包为可执行文件

若希望在没有 Python 环境的机器上运行，可使用 PyInstaller 打包：

```bash
pip install pyinstaller
pyinstaller -F -w -n DeepSeekDesktop pySide6Codex.py
```

- `-F`：单文件
- `-w`：不显示控制台（Windows 下）
- 打包后需在**可执行文件同目录**放置 `.env` 文件
- 若打包体积过大，可排除未用到的模块

---

## 六、使用手册

### 6.1 会话选择窗口

启动后首先进入会话选择界面，分为三部分：

1. **新建对话**：在输入框填写名称（如「C++ 内存优化」），按回车或点击 **➕ 新建对话** 即可进入主界面。
2. **历史对话列表**：按最近更新时间倒序排列，每行显示：
   - 会话名称
   - 占用磁盘大小（如 `2.34 MB`）
   - **🗑 删除** 按钮（会二次确认，删除后不可恢复）
   - 点击行内非按钮区域即可打开该会话。
3. **空列表提示**：无历史对话时显示「暂无历史对话，请在上方新建一个对话。」

> 输入框为空时会提示「请输入对话名称」。

### 6.2 主界面布局

```
┌──────────────────────────────────────────────────────────┐
│ 🔙 切换会话                           当前会话：xxx        │
├───────────────────────────────┬──────────────────────────┤
│                               │  待分析附件：             │
│  对话记录（Markdown 渲染）     │  ├─ [文本] a.cpp         │
│                               │  └─ [图片] b.png         │
│                               │                          │
├───────────────────────────────┴──────────────────────────┤
│ 输入需求，或拖入/选择代码……              [ 发送 ]        │
│                                          [📎 上传文件]    │
│                                          [🗑 清空消息]    │
└──────────────────────────────────────────────────────────┘
```

- **顶部**：切换会话按钮 + 当前会话名称。
- **左侧**：聊天记录区，Markdown 渲染，浅绿背景。
- **右侧**：待分析附件列表。
- **底部**：输入框 + 右侧竖排按钮（发送 / 上传 / 清空）。

### 6.3 发送消息

1. 在输入框输入需求（可多行）。
2. 可选：点击 **📎 上传文件** 添加附件。
3. 点击 **发送**（或程序尚未提供快捷键时，用鼠标点击）。

发送后：

- 输入框内容被清空并显示到聊天区；
- 弹出「🤖 DeepSeek：」后逐字流式输出；
- 输出完成后自动渲染为 Markdown 并保存到本地；
- 生成期间 **发送 / 上传 / 清空 / 切换** 按钮均被禁用。

### 6.4 附件支持

支持的文件类型：

- **文本/代码**：`.c .cpp .h .hpp .cc .cxx .json .txt .md .py .csv .xml .yaml .yml .log .ini .cfg .toml .js .ts .html .css .sh .bat`
  - 内容会以 `===== 文件名 =====` 的形式拼接进用户消息。
- **图片**：`.jpg .jpeg .png .gif .webp`
  - 单张上限 **20 MB**；
  - 保存到会话目录，发送时以 base64 Data URL 提交给多模态模型。

> 其他扩展名会弹出「暂不支持」警告。

### 6.5 模型选择（自动）

- 若本次请求包含图片 → 使用 `deepseek-flash`（多模态）。
- 否则 → 使用 `deepseek-chat`（文本）。
- 单次最大输出 token：`8192`。

### 6.6 代码块复制

助手回复中的每个代码块下方会出现「📋 复制」链接，点击后：

- 代码纯文本写入系统剪贴板；
- 状态栏提示「代码已复制到剪贴板」；
- **保持当前滚动位置**，不会跳回顶部。

### 6.7 切换会话

点击顶部 **🔙 切换会话**：

- 若正在生成回复，会提示「请等待当前回复完成后再切换对话。」；
- 否则关闭主窗口并重新打开选择器。

### 6.8 清空消息

点击 **🗑 清空消息**：

- 二次确认后清空当前会话的全部消息与图片文件；
- 会话本身保留（仍会出现在历史列表中）；
- 状态栏提示「本对话消息已清空」。

---

## 七、数据存储说明

所有数据通过 `QStandardPaths.AppDataLocation` 定位，目录结构如下：

```
<AppData>/sessions/
└── <session_id(32位hex)>/
    ├── meta.json          # {"name", "created_at", "updated_at"}
    ├── messages.json      # 消息数组（role/content）
    └── images/            # 上传的图片文件
```

- **写入方式**：`messages.json` 与 `meta.json` 均采用「临时文件 + 原子替换」，避免写入中断损坏数据。
- **更新时间**：每次保存消息都会同步刷新 `meta.json` 的 `updated_at`，用于历史列表排序。
- **删除会话**：递归删除整个会话目录，**不可恢复**。

> 由于本程序未显式调用 `QApplication.setApplicationName()`，实际根目录名通常取自可执行文件名 / 脚本名（例如 `Python`、`pySide6Codex` 等）。
> 建议先运行一次，并在以下位置查找：
> - Windows：`C:\Users\<用户名>\AppData\Roaming\<AppName>`
> - macOS：`~/Library/Application Support/<AppName>`
> - Linux：`~/.local/share/<AppName>`

---

## 八、关键配置项（`main_window.py`）

| 变量                      | 默认值           | 说明                                   |
| ------------------------- | ---------------- | -------------------------------------- |
| `MODEL_TEXT`              | `deepseek-chat`  | 纯文本模型                             |
| `MODEL_VISION`            | `deepseek-flash` | 多模态模型                             |
| `MAX_TOKENS`              | `8192`           | 单次最大输出 token                     |
| `IMAGE_INLINE_SAFE_BYTES` | `20 MB`          | 单张图片大小上限                       |
| `IMAGE_HISTORY_LIMIT`     | `3`              | 参与请求的最近消息条数（用于图片裁剪） |
| `timeout`                 | `300.0` 秒       | OpenAI 客户端请求超时                  |

如需更换 API 地址，修改 `main_window.py` 顶部：

```python
client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com", timeout=300.0)
```

---

## 九、常见问题（FAQ）

**Q1：启动报错「未设置 DEEPSEEK_API_KEY」并退出？**
A：确认项目根目录存在 `.env` 文件且其中写有 `DEEPSEEK_API_KEY=sk-...`。若使用打包后的 exe，请把 `.env` 放在 exe 同目录。

**Q2：回复很慢或一直卡住？**
A：流式输出受网络影响；`timeout` 默认 300 秒。可在生成期间等待，或关闭程序重试。若被防火墙拦截，请允许访问 `api.deepseek.com`。

**Q3：上传图片提示「图片过大」？**
A：单张图片超过 20 MB 会被拒绝。请压缩或裁剪后重试。

**Q4：历史消息里的图片看不到了？**
A：图片文件可能被手动删除，聊天区会显示「[图片缺失:xxx]」；同时本地 `images/` 目录也可能被清空。

**Q5：为什么很久以前的图片没有发给模型？**
A：为避免超长/超限，程序仅把 **最近 3 条消息** 中的图片转为 Data URL 发送，其余历史图片以 `[图片:名称（历史省略）]` 文本占位。

**Q6：切换会话后原窗口消失，程序也退出了？**
A：在选择器中点击「取消/关闭」会退出程序（当前设计如此）。请确保在会话列表中选择一个历史会话或新建。

**Q7：数据目录找不到？**
A：参见第七节路径。可先用 `python -c "from chat_store import _sessions_root; print(_sessions_root())"` 打印实际路径。

**Q8：能否更换为其他模型？**
A：修改 `main_window.py` 中的 `MODEL_TEXT` / `MODEL_VISION` 即可（需该模型兼容 OpenAI Chat Completions 协议）。

---

## 十、注意事项与限制

- 当前发送**不支持快捷键**（回车会插入换行），请通过「发送」按钮提交。
- 切换会话采用「关闭主窗口 → 重新打开选择器」的方式；若在上一步取消，程序退出。
- 生成过程中点击 **🔙 切换会话** 会被拦截，不会中断当前回复。
- 删除会话与清空消息均为**不可恢复**操作。
- 本项目仅用于个人学习与本地使用，请遵守 DeepSeek 服务条款。
- 请勿将 `.env` 或含密钥的文件公开分享。

---

## 十一、许可

本项目未附带明确许可证，使用前请与作者确认。第三方依赖（PySide6、openai、markdown 等）遵循各自开源协议。