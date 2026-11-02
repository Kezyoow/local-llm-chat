#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件解析模块：把各种格式的文件转成模型能读的文本。

支持：
    文档   .pdf .docx .xlsx .xlsm .pptx .rtf .epub .odt(纯文本部分)
    文本   .txt .md .csv .json .xml .html .htm .log .ini .yaml .yml .toml
    代码   .py .js .ts .java .c .cpp .h .cs .go .rs .php .rb .sh .ps1 .sql
    图片   .png .jpg .jpeg .webp .bmp .gif .tiff   （交给视觉模型，不在这里转文本）

用法（命令行自测）：
    python extract.py 文件1 文件2 ...
"""

import csv
import io
import os
import re
import zipfile

# ---------------------------------------------------------------- 支持的类型
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}

DOC_EXT = {".pdf", ".docx", ".xlsx", ".xlsm", ".pptx", ".rtf", ".epub"}

TEXT_EXT = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl", ".xml",
    ".html", ".htm", ".log", ".ini", ".cfg", ".conf", ".yaml", ".yml",
    ".toml", ".properties", ".env", ".tex", ".rst",
    # 代码
    ".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".java", ".kt", ".c", ".h",
    ".cpp", ".hpp", ".cs", ".go", ".rs", ".php", ".rb", ".swift", ".lua",
    ".sh", ".bash", ".ps1", ".bat", ".sql", ".css", ".scss", ".vue",
}

LEGACY_EXT = {".doc", ".xls", ".ppt"}      # 老二进制格式，明确提示不支持
MAX_FILE_MB = 80


class ExtractError(Exception):
    pass


# ---------------------------------------------------------------- 工具函数
def estimate_tokens(text):
    """粗略估算 token 数：中文约 1.5 字/token，其余约 4 字符/token。"""
    if not text:
        return 0
    cjk = 0
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            cjk += 1
    other = len(text) - cjk
    return int(cjk / 1.5 + other / 4.0) + 1


def _read_text_file(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030", "big5", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _strip_html(text):
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    return re.sub(r"[ \t]+", " ", text)


def _strip_rtf(text):
    text = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    return re.sub(r"\s+", " ", text)


# ---------------------------------------------------------------- 各格式解析
def _pdf(path):
    from pypdf import PdfReader
    reader = PdfReader(path)
    pages = len(reader.pages)
    parts = []
    for i, page in enumerate(reader.pages, 1):
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        t = t.strip()
        if t:
            parts.append(f"[第 {i} 页]\n{t}")
    text = "\n\n".join(parts)
    note = ""
    if not text:
        note = "这个 PDF 没有可提取的文字（可能是扫描件）。请把页面截图后作为图片上传。"
    elif len(text) < pages * 40:
        note = "文字很少，可能是扫描件或图片型 PDF。"
    return text, f"{pages} 页", note


def _docx(path):
    import docx
    d = docx.Document(path)
    parts = [p.text.strip() for p in d.paragraphs if p.text.strip()]
    for ti, table in enumerate(d.tables, 1):
        rows = []
        for row in table.rows:
            cells = [c.text.strip().replace("\n", " ") for c in row.cells]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            parts.append(f"[表格 {ti}]\n" + "\n".join(rows))
    return "\n".join(parts), f"{len(d.paragraphs)} 段", ""


def _xlsx(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets[:5]:
        out.append(f"[工作表: {ws.title}]")
        n = 0
        for row in ws.iter_rows(values_only=True):
            if row is None:
                continue
            cells = ["" if v is None else str(v) for v in row[:30]]
            if any(c.strip() for c in cells):
                out.append(" | ".join(cells).rstrip(" |"))
                n += 1
            if n >= 1500:
                out.append("…（该表行数过多，已截断前 1500 行）")
                break
    if len(wb.worksheets) > 5:
        out.append(f"…（共 {len(wb.worksheets)} 个工作表，只读取前 5 个）")
    wb.close()
    return "\n".join(out), f"{len(out)} 行", ""


def _pptx(path):
    from pptx import Presentation
    prs = Presentation(path)
    out = []
    for i, slide in enumerate(prs.slides, 1):
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                t = shape.text_frame.text.strip()
                if t:
                    texts.append(t)
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells]
                    if any(cells):
                        texts.append(" | ".join(cells))
        if texts:
            out.append(f"[第 {i} 页]\n" + "\n".join(texts))
    return "\n\n".join(out), f"{len(prs.slides)} 页", ""


def _csv(path):
    text = _read_text_file(path)
    try:
        dialect = csv.Sniffer().sniff(text[:4000])
        delim = dialect.delimiter
    except Exception:
        delim = ","
    rows = text.splitlines()
    if len(rows) > 2000:
        rows = rows[:2000] + ["…（行数过多，已截断前 2000 行）"]
    return "\n".join(rows), f"{len(rows)} 行（分隔符 {delim!r}）", ""


def _html(path):
    return _strip_html(_read_text_file(path)), "HTML", ""


def _epub(path):
    parts = []
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith((".xhtml", ".html", ".htm"))]
        names.sort()
        for n in names:
            try:
                raw = z.read(n).decode("utf-8", "replace")
            except Exception:
                continue
            t = _strip_html(raw).strip()
            if t:
                parts.append(t)
    return "\n\n".join(parts), f"{len(parts)} 个章节", ""


def _rtf(path):
    return _strip_rtf(_read_text_file(path)), "RTF", ""


HANDLERS = {
    ".pdf": _pdf, ".docx": _docx, ".xlsx": _xlsx, ".xlsm": _xlsx,
    ".pptx": _pptx, ".csv": _csv, ".tsv": _csv, ".html": _html,
    ".htm": _html, ".epub": _epub, ".rtf": _rtf,
}


# ---------------------------------------------------------------- 对外接口
def extract(path):
    """返回 dict: kind/path/name/ext/size/mb/text/chars/tokens/detail/note/error"""
    name = os.path.basename(path)
    ext = os.path.splitext(path)[1].lower()
    info = {
        "kind": "text", "path": path, "name": name, "ext": ext,
        "size": 0, "mb": 0.0, "text": "", "chars": 0, "tokens": 0,
        "detail": "", "note": "", "error": "",
    }
    try:
        if not os.path.isfile(path):
            raise ExtractError("文件不存在")
        size = os.path.getsize(path)
        info["size"] = size
        info["mb"] = round(size / 1024 / 1024, 2)
        if size > MAX_FILE_MB * 1024 * 1024:
            raise ExtractError(f"文件超过 {MAX_FILE_MB}MB，请拆分后再上传")

        if ext in IMAGE_EXT:
            from PIL import Image
            with Image.open(path) as im:
                info["detail"] = f"{im.width}×{im.height} {im.format}"
                try:
                    info["text"] = ""       # 图片交给视觉模型
                except Exception:
                    pass
            info["kind"] = "image"
            return info

        if ext in LEGACY_EXT:
            raise ExtractError(f"{ext} 是旧版二进制格式，请另存为 "
                               f"{ {'.doc': '.docx', '.xls': '.xlsx', '.ppt': '.pptx'}[ext] } 后再传")

        if ext in HANDLERS:
            text, detail, note = HANDLERS[ext](path)
            info["detail"] = detail
            info["note"] = note
        elif ext in TEXT_EXT:
            text = _read_text_file(path)
            info["detail"] = "纯文本"
        else:
            # 未知扩展名，按文本尝试（能解码就当文本用）
            text = _read_text_file(path)
            if text.count("\x00") > 0:
                raise ExtractError(f"不支持的二进制格式 {ext or '(无扩展名)'}")
            info["detail"] = "按文本读取"

        text = (text or "").replace("\x00", "").strip()
        info["text"] = text
        info["chars"] = len(text)
        info["tokens"] = estimate_tokens(text)
        if not text:
            info["note"] = info["note"] or "没有提取到任何文字内容"
        return info
    except ExtractError as e:
        info["error"] = str(e)
        return info
    except Exception as e:
        info["error"] = f"{type(e).__name__}: {e}"
        return info


def build_context(infos, budget_tokens=20000):
    """把多个文件的文本拼成上下文块，超出预算时按比例截断。

    返回 (context_text, warnings)
    """
    docs = [i for i in infos if i.get("kind") == "text" and i.get("text")]
    warnings = []
    for i in infos:
        if i.get("error"):
            warnings.append(f"{i['name']}: {i['error']}")
        elif i.get("note"):
            warnings.append(f"{i['name']}: {i['note']}")

    if not docs:
        return "", warnings

    total = sum(i["tokens"] for i in docs)
    parts = []
    for idx, i in enumerate(docs, 1):
        text = i["text"]
        if total > budget_tokens:
            keep = max(500, int(len(text) * budget_tokens / total))
            if keep < len(text):
                text = text[:keep] + f"\n…[内容过长已截断，原文共 {i['chars']} 字]"
                warnings.append(f"{i['name']}: 内容过长，已截断到约 {keep} 字")
        head = f"===== 文件 {idx}: {i['name']}"
        if i.get("detail"):
            head += f"（{i['detail']}）"
        head += f"，{i['chars']} 字 ====="
        parts.append(head + "\n" + text)
    return "\n\n".join(parts), warnings


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print("用法: python extract.py 文件1 [文件2 ...]")
        sys.exit(0)
    for p in sys.argv[1:]:
        r = extract(p)
        print("=" * 70)
        print(f"{r['name']}  [{r['ext']}]  {r['mb']}MB  类型={r['kind']}")
        print(f"  详情: {r['detail']}   字数: {r['chars']}   估算 tokens: {r['tokens']}")
        if r["error"]:
            print(f"  错误: {r['error']}")
        if r["note"]:
            print(f"  提示: {r['note']}")
        if r["text"]:
            head = r["text"][:300].replace("\n", " / ")
            print(f"  预览: {head}")
