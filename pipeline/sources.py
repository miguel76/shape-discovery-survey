"""The dump files of a KG: local files, or files downloaded from a URL or from figshare.

Each entry of the `files` list in data/<KG>/kg.json is one of:

  "name.nq.gz"                              a file in data/<KG>/
  {"url": "https://...", "name": "x.nq.gz", "md5": "..."}
                                            a file to download; name defaults to the last
                                            segment of the URL, md5 (optional) is checked
  {"figshare": "10.6084/m9.figshare.29066711.v14", "match": "*.nq.gz"}
                                            the files of a figshare item whose names match
                                            the pattern (default: all of them). The DOI, a
                                            doi.org or figshare URL, or "29066711.v14" are
                                            accepted; without a version, the latest one.

Downloads go to data/<KG>/download/ and are reused while their size and MD5 match what the
source declares (figshare declares both). Each download is recorded next to the file in
<name>.source.json (the URL, the figshare item and version, the MD5). When figshare cannot be
reached, the matching files already in data/<KG>/download/ are used: earlier downloads of the
same item as they are, files put there by hand with a warning (they cannot be verified).
"""
import fnmatch
import hashlib
import json
import os
import re
import shutil
import urllib.request
from pathlib import Path

FIGSHARE_API = os.environ.get("FIGSHARE_API", "https://api.figshare.com/v2")
USER_AGENT = "shape-discovery-survey (https://github.com/miguel76/shape-discovery-survey)"


def kg_files(kg_dir, entries, log=print):
    """Local paths of the files listed in a kg.json `files` (or `ontologies`) entry list,
    downloading the remote ones that are not already in data/<KG>/download/."""
    paths = []
    for entry in entries:
        if isinstance(entry, str):
            paths.append(Path(kg_dir) / entry)
        elif "url" in entry:
            name = entry.get("name") or entry["url"].rstrip("/").rsplit("/", 1)[-1]
            paths.append(download(entry["url"], Path(kg_dir) / "download" / name, md5=entry.get("md5"),
                                  provenance={"url": entry["url"]}, log=log))
        elif "figshare" in entry:
            paths += figshare_files(kg_dir, entry["figshare"], entry.get("match", "*"), log)
        else:
            raise ValueError(f"unknown file entry in kg.json: {entry}")
    return paths


def parse_figshare(ref):
    """(article id, version or None) from a figshare DOI, URL or 'id[.vN]'."""
    m = re.search(r"(?:figshare\.|^)(\d+)(?:\.v(\d+))?/?$", ref.strip()) or \
        re.search(r"figshare\.com/articles/(?:[^/]+/)*?(\d+)(?:/(\d+))?/?$", ref)
    if not m:
        raise ValueError(f"not a figshare DOI or item: {ref}")
    return int(m.group(1)), (int(m.group(2)) if m.group(2) else None)


def figshare_item(ref):
    article, version = parse_figshare(ref)
    url = f"{FIGSHARE_API}/articles/{article}" + (f"/versions/{version}" if version else "")
    with urlopen(url) as resp:
        item = json.load(resp)
    return article, item.get("version", version), item


def figshare_files(kg_dir, ref, pattern, log=print):
    try:
        article, version, item = figshare_item(ref)
    except OSError:
        # offline: use the matching files already in download/ (see offline_files)
        found = offline_files(Path(kg_dir) / "download", ref, pattern, log)
        if found:
            return found
        raise

    files = [f for f in item.get("files", []) if fnmatch.fnmatch(f["name"], pattern)]
    if not files:
        names = ", ".join(f["name"] for f in item.get("files", []))
        raise FileNotFoundError(f"figshare item {article} v{version} has no file matching {pattern!r} ({names})")
    out = []
    for f in files:
        md5 = f.get("computed_md5") or f.get("supplied_md5") or None
        out.append(download(f["download_url"], Path(kg_dir) / "download" / f["name"], md5=md5, size=f.get("size"),
                            provenance={"figshare": ref, "article": article, "version": version,
                                        "doi": item.get("doi"), "file_id": f.get("id"),
                                        "url": f["download_url"]},
                            log=log))
    return out


def offline_files(download_dir, ref, pattern, log=print):
    """Files of download_dir matching pattern, for when figshare cannot be reached. Files
    downloaded earlier from the same item (per their .source.json) are used as they are; other
    matching files, e.g. downloaded by hand, are used with a warning, since they cannot be
    verified."""
    files = sorted(p for p in download_dir.glob(pattern) if not p.name.endswith((".part", ".source.json")))
    article, version = parse_figshare(ref)
    out = []
    for p in files:
        prov = p.with_name(p.name + ".source.json")
        rec = json.loads(prov.read_text()) if prov.exists() else {}
        if rec.get("article") == article and (version is None or rec.get("version") == version):
            out.append(p)
        elif not rec:
            log(f"[download] figshare unreachable; using {p}, which cannot be verified against item {ref}")
            out.append(p)
    if out:
        log(f"[download] figshare unreachable; using {len(out)} file(s) already in {download_dir}")
    return out


def download(url, dest, md5=None, size=None, provenance=None, log=print):
    """Download url to dest unless dest already holds the expected file."""
    dest = Path(dest)
    if dest.exists() and (size is None or dest.stat().st_size == size) and (md5 is None or file_md5(dest) == md5):
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    log(f"[download] {url} -> {dest}")
    part = dest.with_name(dest.name + ".part")
    with urlopen(url) as resp, open(part, "wb") as out:
        shutil.copyfileobj(resp, out, length=1 << 20)
    if size is not None and part.stat().st_size != size:
        raise IOError(f"{url}: got {part.stat().st_size} bytes, expected {size}")
    got = file_md5(part)
    if md5 is not None and got != md5:
        raise IOError(f"{url}: MD5 {got}, expected {md5}")
    part.replace(dest)
    dest.with_name(dest.name + ".source.json").write_text(
        json.dumps({**(provenance or {"url": url}), "md5": got, "size": dest.stat().st_size}, indent=2) + "\n")
    return dest


def urlopen(url):
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=120)
    except OSError as e:  # URLError, HTTPError and timeouts
        raise OSError(f"cannot download {url}: {e}. Check the network access to that host, or download "
                      "the file by hand into data/<KG>/download/") from e


def file_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
