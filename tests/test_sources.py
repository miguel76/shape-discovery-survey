#!/usr/bin/env python3
"""Checks of pipeline/sources.py: figshare references and downloads.

usage: python tests/test_sources.py

The downloads are tested against a local HTTP server that answers like the figshare API
(article metadata with files, their sizes and MD5s). This tests the download logic, not
figshare itself.
"""
import hashlib
import http.server
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

DUMP = b"<http://example.org/s> <http://example.org/p> <http://example.org/o> <http://example.org/g> .\n" * 1000
OTHER = b"not a dump\n"


class Handler(http.server.BaseHTTPRequestHandler):
    corrupt = False
    hits = []

    def do_GET(self):
        Handler.hits.append(self.path)
        port = self.server.server_address[1]
        files = [{"id": 1, "name": "kg_2026.nq.gz", "size": len(DUMP), "computed_md5": hashlib.md5(DUMP).hexdigest(),
                  "download_url": f"http://127.0.0.1:{port}/files/1"},
                 {"id": 2, "name": "README.txt", "size": len(OTHER), "computed_md5": hashlib.md5(OTHER).hexdigest(),
                  "download_url": f"http://127.0.0.1:{port}/files/2"}]
        if self.path in ("/v2/articles/29066711/versions/14", "/v2/articles/29066711"):
            body = json.dumps({"version": 14, "doi": "10.6084/m9.figshare.29066711.v14", "files": files}).encode()
        elif self.path == "/files/1":
            body = DUMP[:-10] if Handler.corrupt else DUMP
        elif self.path == "/files/2":
            body = OTHER
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    os.environ["FIGSHARE_API"] = f"http://127.0.0.1:{server.server_address[1]}/v2"
    import sources  # reads FIGSHARE_API
    failures = []

    def check(cond, what):
        print(("ok   " if cond else "FAIL ") + what)
        if not cond:
            failures.append(what)

    for ref, expected in [("10.6084/m9.figshare.29066711.v14", (29066711, 14)),
                          ("https://doi.org/10.6084/m9.figshare.29066711.v14", (29066711, 14)),
                          ("10.6084/m9.figshare.29066711", (29066711, None)),
                          ("29066711.v14", (29066711, 14)),
                          ("https://figshare.com/articles/dataset/CCKG/29066711/14", (29066711, 14)),
                          ("https://figshare.com/articles/dataset/CCKG/29066711", (29066711, None))]:
        check(sources.parse_figshare(ref) == expected, f"parse {ref}")

    with tempfile.TemporaryDirectory() as tmp:
        kg_dir = Path(tmp)
        (kg_dir / "local.ttl").write_text("")
        entries = ["local.ttl", {"figshare": "10.6084/m9.figshare.29066711.v14", "match": "*.nq.gz"}]
        paths = sources.kg_files(kg_dir, entries, log=lambda m: None)
        check([p.name for p in paths] == ["local.ttl", "kg_2026.nq.gz"], "local file kept, only the matching file selected")
        check(paths[1].read_bytes() == DUMP, "downloaded content")
        prov = json.loads((kg_dir / "download" / "kg_2026.nq.gz.source.json").read_text())
        check(prov["version"] == 14 and prov["md5"] == hashlib.md5(DUMP).hexdigest(), "provenance recorded")
        n = len([h for h in Handler.hits if h.startswith("/files/")])
        sources.kg_files(kg_dir, entries, log=lambda m: None)
        check(len([h for h in Handler.hits if h.startswith("/files/")]) == n, "existing download reused")
        paths[1].write_bytes(b"tampered")
        sources.kg_files(kg_dir, entries, log=lambda m: None)
        check(paths[1].read_bytes() == DUMP, "file with a wrong MD5 downloaded again")
        Handler.corrupt = True
        paths[1].unlink()
        try:
            sources.kg_files(kg_dir, entries, log=lambda m: None)
            check(False, "truncated download rejected")
        except IOError:
            check(not paths[1].exists(), "truncated download rejected")
        Handler.corrupt = False
        try:
            sources.kg_files(kg_dir, [{"figshare": "29066711.v14", "match": "*.ttl"}], log=lambda m: None)
            check(False, "no matching file reported")
        except FileNotFoundError:
            check(True, "no matching file reported")
        # offline: figshare unreachable, the earlier download of the same item is used
        sources.kg_files(kg_dir, entries, log=lambda m: None)  # download it again
        sources.FIGSHARE_API = "http://127.0.0.1:9/v2"  # nothing listens on port 9
        paths = sources.kg_files(kg_dir, entries, log=lambda m: None)
        check(paths[1].read_bytes() == DUMP, "offline: earlier download of the same item used")
        try:
            sources.kg_files(kg_dir, [{"figshare": "29066711.v15", "match": "*.nq.gz"}], log=lambda m: None)
            check(False, "offline: download of another version not used")
        except OSError:
            check(True, "offline: download of another version not used")
        sources.FIGSHARE_API = os.environ["FIGSHARE_API"]
        url = f"http://127.0.0.1:{server.server_address[1]}/files/2"
        p = sources.kg_files(kg_dir, [{"url": url, "name": "readme.txt", "md5": hashlib.md5(OTHER).hexdigest()}],
                             log=lambda m: None)[0]
        check(p.read_bytes() == OTHER, "plain URL entry")
    server.shutdown()
    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
