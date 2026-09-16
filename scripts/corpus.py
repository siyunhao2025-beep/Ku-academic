#!/usr/bin/env python3
"""Local PDF ingestion and explicitly authorized HTTPS downloads. No OCR or model calls."""
from __future__ import annotations
import argparse
import ipaddress
import json
from pathlib import Path
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from research import doi, read, safe_path, sha, utc, write


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def public_url(url, hosts):
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or u.username or u.password or u.port not in (None, 443) or u.hostname not in hosts:
        raise ValueError("URL must use HTTPS and an explicitly allowed host")
    for entry in socket.getaddrinfo(u.hostname, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(entry[4][0]).is_global:
            raise ValueError("Private/non-global network address blocked")


def fetch_pdf(url, target, hosts, max_bytes=40_000_000):
    """No cookies, credentials or paywall bypass; redirects rechecked before following."""
    target = Path(target)
    if target.exists():
        raise FileExistsError("PDF destination already exists")
    opener = urllib.request.build_opener(NoRedirect())
    data = bytearray()
    for _ in range(6):
        public_url(url, hosts)
        req = urllib.request.Request(url, headers={"User-Agent": "ResearchMother/0.1"})
        try:
            with opener.open(req, timeout=25) as response:
                while True:
                    chunk = response.read(min(1024 * 1024, max_bytes - len(data) + 1))
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > max_bytes:
                        raise ValueError("PDF exceeds size limit")
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (301, 302, 303, 307, 308):
                raise
            location = exc.headers.get("Location")
            if not location:
                raise ValueError("Redirect without Location") from exc
            url = urllib.parse.urljoin(url, location)
    else:
        raise ValueError("Too many redirects")
    if not bytes(data).startswith(b"%PDF-"):
        raise ValueError("Server did not return PDF bytes; no HTML saved as PDF")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"path": str(target), "sha256": sha(target), "final_url": url, "at": utc()}


def download_manifest(manifest, output, hosts):
    rows = read(manifest)
    output = Path(output)
    if output.exists():
        raise FileExistsError("Choose a fresh download directory")
    output.mkdir(parents=True)
    records = []
    for i, row in enumerate(rows):
        result = {"id": row.get("id", str(i)), "requested_url": row.get("url", "")}
        try:
            if row.get("authorization") not in {"open_access_verified", "user_authorized"} or not row.get("access_basis"):
                raise ValueError("Explicit access authorization and its basis are required")
            result.update(fetch_pdf(row["url"], output / f"paper-{i+1:04d}.pdf", hosts))
            result["status"] = "downloaded_not_read"
        except Exception as exc:
            result.update(status="failed", error_type=type(exc).__name__)
        records.append(result)
        write(output / "downloads.json", records)
    return records


def ingest(manifest, output):
    from pypdf import PdfReader
    manifest = Path(manifest)
    output = Path(output)
    if output.exists():
        raise FileExistsError("Choose a new corpus directory; originals are never overwritten")
    rows = read(manifest)
    output.mkdir(parents=True)
    report, seen = [], set()
    for i, row in enumerate(rows):
        result = {"id": row.get("id", ""), "status": "pending"}
        try:
            source = Path(row["path"])
            if not source.is_absolute():
                source = safe_path(manifest.parent, row["path"])
            checksum = sha(source)
            ident = doi(row.get("doi")) or row["id"]
            if not ident:
                raise ValueError("A paper ID or DOI is required")
            if checksum in seen or ident in seen:
                result.update(status="duplicate", sha256=checksum)
                report.append(result)
                continue
            reader = PdfReader(source)
            if reader.is_encrypted:
                raise ValueError("Encrypted PDF requires an authorized decrypted copy")
            if len(reader.pages) > 1000:
                raise ValueError("PDF page count exceeds batch limit")
            pages = []
            for number, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ""
                pages.append({"page": number, "text": text,
                              "needs_visual_review": True, "low_text_warning": len(text.strip()) < 80})
            if not any(p["text"].strip() for p in pages):
                raise ValueError("No extractable text; inspect page images, use OCR only as last resort")
            filename = f"paper-{i+1:04d}.pages.json"
            write(output / filename, pages)
            result.update(id=ident, sha256=checksum, source=str(source), journal=row.get("journal", ""),
                          article_type=row.get("article_type", ""), author_group=row.get("author_group", ""),
                          split=row.get("split", "unassigned"), pages_file=filename,
                          pages=len(pages), full_text_read=False, visual_checked=False,
                          metadata_verified=False, status="text_extracted_not_read")
            seen.update((ident, checksum))
        except Exception as exc:
            result.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        report.append(result)
        write(output / "corpus.json", report)
    write(output / "corpus.json", report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    ing = sub.add_parser("ingest"); ing.add_argument("manifest"); ing.add_argument("output")
    down = sub.add_parser("download"); down.add_argument("manifest"); down.add_argument("output")
    down.add_argument("--allow-host", action="append", required=True)
    a = p.parse_args()
    try:
        rows = ingest(a.manifest, a.output) if a.command == "ingest" else download_manifest(a.manifest, a.output, set(a.allow_host))
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 2 if any(r["status"] == "failed" for r in rows) else 0
    except Exception as exc:
        print(json.dumps({"status": "error", "type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
