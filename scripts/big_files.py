#!/usr/bin/env python3
"""List a repo's big tracked files and how to treat each one, before anyone reads anything.

    python3 scripts/big_files.py                  # the repo you're in, files of 50 KB and up
    python3 scripts/big_files.py ~/code/app --min-kb 30 --top 60

Every file a reader opens whole is carried on every later turn of that session, so one
400 KB fixture read early costs far more than its own size. This sorts the big files into:

  skip     lockfiles, vendored, minified, build output, source maps: never read
  binary   images, archives, databases: never read as text (look at an image as an image)
  data     JSON, CSV, SQL dumps, logs, notebooks, fixtures: sample, never read whole
  source   code and docs: read by outline and section; at ~60 KB and up, a split candidate

Standard library only. Tokens are estimated at 4 bytes each.
"""
import argparse
import hashlib
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

LOCKS = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock",
         "gemfile.lock", "poetry.lock", "uv.lock", "cargo.lock", "composer.lock",
         "podfile.lock", "go.sum", "pipfile.lock", "mix.lock", "flake.lock"}
SKIP_DIRS = ("vendor/", "node_modules/", "dist/", "build/", "public/assets/", "public/packs/",
             "third_party/", ".yarn/", "coverage/", "tmp/")
SKIP_SUFFIXES = (".min.js", ".min.css", ".map", ".bundle.js", ".chunk.js", ".pb.go", "_pb2.py")
DATA_EXT = {".json", ".jsonl", ".ndjson", ".geojson", ".csv", ".tsv", ".sql", ".xml", ".log",
            ".ipynb", ".yml", ".yaml", ".txt", ".har", ".ics", ".vcf", ".parquet", ".dump"}
DATA_DIRS = ("fixtures/", "seeds/", "data/", "testdata/", "samples/", "spec/cassettes/",
             "test/cassettes/", "test/vcr_cassettes/")
SPLIT_KB = 60

HOW = {
    "skip": "don't read",
    "binary": "don't read as text",
    "data": "sample: head -c 2000, jq 'keys', xsv headers / count, sqlite3 .schema",
    "source": "outline (rg -n '^(def|class|function|export) ') then read sections",
}


def kind(path: str, head: bytes) -> str:
    low = path.lower()
    name = low.rsplit("/", 1)[-1]
    if name in LOCKS or low.endswith(SKIP_SUFFIXES) or any(f"/{d}" in f"/{low}" for d in SKIP_DIRS):
        return "skip"
    if b"\0" in head:
        return "binary"
    if Path(low).suffix in DATA_EXT or any(f"/{d}" in f"/{low}" for d in DATA_DIRS):
        return "data"
    # One very long line is generated, whatever the extension says.
    if head and b"\n" not in head[:4096] and len(head) >= 4096:
        return "skip"
    return "source"


def long_lines(p: Path):
    """Bytes in lines over 2,000 characters, and whether any of it is base64 data URIs.
    That's an image or a dataset pasted into code: a reader pays for all of it to see a
    few lines of logic around it."""
    data = p.read_bytes()
    long = sum(len(line) for line in data.split(b"\n") if len(line) > 2000)
    return long, b";base64," in data


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--min-kb", type=float, default=50, help="list files at least this big")
    ap.add_argument("--top", type=int, default=40, help="list at most this many")
    args = ap.parse_args()
    root = Path(args.repo).resolve()
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], check=True,
                             capture_output=True).stdout
    except subprocess.CalledProcessError as e:
        sys.exit(e.stderr.decode().strip() or "not a git repo")

    rows, totals, by_hash = [], defaultdict(lambda: [0, 0]), defaultdict(list)
    for rel in filter(None, out.decode("utf-8", "replace").split("\0")):
        p = root / rel
        if not p.is_file():
            continue  # deleted in the working tree, or a submodule
        size = p.stat().st_size
        with p.open("rb") as f:
            head = f.read(8192)
        k = kind(rel, head)
        totals[k][0] += 1
        totals[k][1] += size
        if size >= args.min_kb * 1024:
            rows.append((size, k, rel))
            by_hash[hashlib.sha1(p.read_bytes()).hexdigest()].append(rel)

    rows.sort(reverse=True)
    print(f"{'size':>9}  {'~tokens':>8}  {'kind':<6}  file")
    for size, k, rel in rows[: args.top]:
        flag = ""
        if k == "source":
            long, b64 = long_lines(root / rel)
            if long > size / 2:
                flag = f"  <- {human(long)} in long lines" + (" (base64 data URIs)" if b64 else "")
            elif size >= SPLIT_KB * 1024:
                flag = "  <- split candidate"
        tokens = "-" if k == "binary" else f"{size // 4 // 1000}k"
        print(f"{human(size):>9}  {tokens:>8}  {k:<6}  {rel}{flag}")
    if len(rows) > args.top:
        print(f"... and {len(rows) - args.top} more of {args.min_kb:g} KB and up (--top)")

    dupes = sorted((v for v in by_hash.values() if len(v) > 1),
                   key=lambda v: -(root / v[0]).stat().st_size * (len(v) - 1))
    if dupes:
        wasted = sum((root / v[0]).stat().st_size * (len(v) - 1) for v in dupes)
        print(f"\nidentical copies ({len(dupes)} sets, {human(wasted)} in the extra copies):")
        for v in dupes[:10]:
            print(f"  {len(v)} x {human((root / v[0]).stat().st_size):>8}  " + ", ".join(v[:4])
                  + (f", +{len(v) - 4} more" if len(v) > 4 else ""))
        if len(dupes) > 10:
            print(f"  ... and {len(dupes) - 10} more sets")

    print(f"\n{'kind':<6}  {'files':>6}  {'size':>9}  how to read")
    for k in ("skip", "binary", "data", "source"):
        n, size = totals[k]
        if n:
            print(f"{k:<6}  {n:>6}  {human(size):>9}  {HOW[k]}")


if __name__ == "__main__":
    main()
