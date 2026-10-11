"""Collect permitted public documents and turn them into text sections.

Sources: (1) official SBI URLs fetched politely (robots.txt respected),
(2) manually imported local files from data/sbi_docs/ (PDF, HTML, TXT) when a
site cannot be fetched. Nothing is fabricated: unknown titles/URLs stay explicit.
"""
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional
from urllib import robotparser
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "BankMateAI-EducationalProject/1.0 (student project; public documents only)"
ALLOWED_HOST_SUFFIXES = ("sbi.co.in", "sbi.bank.in")


class DocumentFetchError(Exception):
    pass


@dataclass
class Section:
    text: str
    section_title: Optional[str] = None
    page: Optional[int] = None


@dataclass
class LoadedDocument:
    source_url: str
    title: str
    sections: list = field(default_factory=list)
    retrieval_date: str = field(default_factory=lambda: date.today().isoformat())
    origin: str = "web"  # "web" | "manual"


# ---------------- HTML ----------------
def html_to_document(html: str, source_url: str, fallback_title: str = "", origin: str = "web") -> LoadedDocument:
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.get_text(strip=True) if soup.title else "") or fallback_title or source_url
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "form", "svg", "iframe"]):
        tag.decompose()
    body = soup.body or soup
    sections, heading, buf = [], None, []

    def flush():
        text = " ".join(buf).strip()
        if len(text) >= 40:
            sections.append(Section(text=text, section_title=heading))
        buf.clear()

    for el in body.find_all(["h1", "h2", "h3", "h4", "p", "li", "td"]):
        if el.name in ("p", "li", "td") and el.find_parent(["p", "li", "td"]):
            continue  # avoid duplicating nested text
        text = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
        if not text:
            continue
        if el.name.startswith("h"):
            flush()
            heading = text[:150]
        elif len(text) >= 20:
            buf.append(text)
    flush()
    return LoadedDocument(source_url=source_url, title=title, sections=sections, origin=origin)


# ---------------- PDF ----------------
_HEADING_RE = re.compile(r"^(\d+(\.\d+)*[.)]?\s+[A-Z][^.]{3,80}|[A-Z][A-Z &/,\-]{6,80})$")


def pdf_to_document(data: bytes, source_url: str, title: str, origin: str = "web") -> LoadedDocument:
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
    except Exception as exc:  # pypdf raises many distinct errors for corrupt files
        raise DocumentFetchError(f"Could not read PDF: {exc}") from exc
    sections, heading = [], None
    for page_no, text in pages:
        buf = []

        def flush():
            body = re.sub(r"\s+", " ", " ".join(buf)).strip()
            if len(body) >= 40:
                sections.append(Section(text=body, section_title=heading, page=page_no))
            buf.clear()

        for line in (ln.strip() for ln in text.splitlines()):
            if not line:
                continue
            if _HEADING_RE.match(line) and len(line) <= 90:
                flush()
                heading = line
            else:
                buf.append(line)
        flush()
    if not sections:
        raise DocumentFetchError("PDF contained no extractable text (it may be scanned images).")
    return LoadedDocument(source_url=source_url, title=title, sections=sections, origin=origin)


# ---------------- plain text ----------------
def text_to_document(text: str, source_url: str, title: str, origin: str = "manual") -> LoadedDocument:
    sections = [Section(text=re.sub(r"\s+", " ", p).strip()) for p in re.split(r"\n\s*\n", text)
                if len(p.strip()) >= 40]
    return LoadedDocument(source_url=source_url, title=title, sections=sections, origin=origin)


# ---------------- fetching ----------------
def _check_allowed(url: str) -> None:
    host = urlparse(url).hostname or ""
    if not any(host == h or host.endswith("." + h) for h in ALLOWED_HOST_SUFFIXES):
        raise DocumentFetchError(f"Host '{host}' is not an approved official SBI domain.")
    parsed = urlparse(url)
    rp = robotparser.RobotFileParser()
    try:
        robots = requests.get(f"{parsed.scheme}://{parsed.netloc}/robots.txt",
                              headers={"User-Agent": USER_AGENT}, timeout=15)
        if robots.status_code == 200:
            rp.parse(robots.text.splitlines())
            if not rp.can_fetch(USER_AGENT, url):
                raise DocumentFetchError("robots.txt disallows fetching this URL; import it manually instead.")
    except requests.RequestException:
        pass  # robots.txt unreachable: proceed, the page fetch below will fail visibly if blocked


def _title_from_url(url: str) -> str:
    """Readable title from the .pdf file name in the URL (last resort when no title is given)."""
    for seg in reversed(urlparse(url).path.split("/")):
        if seg.lower().endswith(".pdf"):
            return unquote(seg)[:-4].replace("+", " ").replace("_", " ").strip() or "PDF document"
    return "PDF document"


def fetch_source(url: str, timeout: int = 60, title: Optional[str] = None) -> LoadedDocument:
    _check_allowed(url)
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    except requests.RequestException as exc:
        raise DocumentFetchError(f"Network error ({type(exc).__name__}): could not download. "
                                 "Check internet/proxy, or import manually.") from exc
    if resp.status_code != 200:
        raise DocumentFetchError(f"HTTP {resp.status_code} (site may block automated access; import manually).")
    ctype = resp.headers.get("Content-Type", "").lower()
    if "pdf" in ctype or ".pdf" in urlparse(url).path.lower():
        return pdf_to_document(resp.content, url, title=title or _title_from_url(url))
    doc = html_to_document(resp.text, url)
    if title:
        doc.title = title
    return doc


# ---------------- manual import ----------------
def _norm(name: str) -> str:
    """Compare file names loosely: ignore case, spaces, underscores, dashes and the extension."""
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return re.sub(r"[^a-z0-9]", "", stem.lower())


def load_local_documents(docs_dir: Path) -> tuple:
    """Returns (documents, problems). Optional manifest data/sbi_docs/sources.json:
    {"Private Policy.pdf": {"title": "...", "source_url": "https://..."}}
    File names in the manifest are matched loosely (case, spaces and underscores ignored)."""
    docs, problems = [], []
    docs_dir = Path(docs_dir)
    if not docs_dir.exists():
        return docs, problems
    manifest = {}
    mpath = docs_dir / "sources.json"
    if mpath.exists():
        try:
            raw = json.loads(mpath.read_text(encoding="utf-8"))
            manifest = {_norm(k): v for k, v in raw.items()}
        except json.JSONDecodeError as exc:
            problems.append((str(mpath), f"sources.json is not valid JSON: {exc}"))
    for path in sorted(docs_dir.iterdir()):
        if path.suffix.lower() not in (".pdf", ".html", ".htm", ".txt"):
            continue
        meta = manifest.get(_norm(path.name), {})
        title = meta.get("title", path.stem.replace("_", " "))
        url = meta.get("source_url", f"manual-import:{path.name}")
        try:
            if path.suffix.lower() == ".pdf":
                docs.append(pdf_to_document(path.read_bytes(), url, title, origin="manual"))
            elif path.suffix.lower() in (".html", ".htm"):
                docs.append(html_to_document(path.read_text(encoding="utf-8", errors="ignore"),
                                             url, fallback_title=title, origin="manual"))
            else:
                docs.append(text_to_document(path.read_text(encoding="utf-8", errors="ignore"), url, title))
        except DocumentFetchError as exc:
            problems.append((path.name, str(exc)))
    return docs, problems