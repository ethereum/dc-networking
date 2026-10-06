#!/usr/bin/env python3
"""Build free-running-committees.html (one self-contained file) from src/.

  src/shell.html        page skeleton with /*INLINE:x*/, /*DATA:x*/ and {{KEY}} slots
  src/*.css, src/*.js   inlined verbatim
  src/text/KEY.html     narrative fragments, one per {{KEY}}
  results/traces.json   design traces (sim/designs.py traces) -> window.FRC_TRACES
  results/ideal.json    ideal-model lags in seconds, per design id -> window.FRC_IDEAL

Usage: python3 build.py
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "src"
OUT = HERE / "free-running-committees.html"


def main():
    page = (SRC / "shell.html").read_text()

    def inline(m):
        return (SRC / m.group(1)).read_text()

    page = re.sub(r"/\*INLINE:([\w.-]+)\*/", inline, page)

    def data(m):
        name = m.group(1)
        p = HERE / "results" / f"{name}.json"
        if not p.exists():
            print(f"warning: {p.relative_to(HERE)} missing", file=sys.stderr)
            return "null"
        # compact, and safe inside <script>
        return json.dumps(json.loads(p.read_text()), separators=(",", ":")).replace("</", "<\\/")

    page = re.sub(r"/\*DATA:([\w.-]+)\*/null", data, page)

    missing = []

    def text(m):
        key = m.group(1)
        p = SRC / "text" / f"{key}.html"
        if not p.exists():
            missing.append(key)
            return f'<p class="muted">[missing: {key}]</p>'
        return p.read_text().strip()

    page = re.sub(r"\{\{([A-Z0-9_]+)\}\}", text, page)
    OUT.write_text(page)
    kb = OUT.stat().st_size / 1024
    print(f"wrote {OUT.name} ({kb:.0f} kB)" + (f"; missing text: {', '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
