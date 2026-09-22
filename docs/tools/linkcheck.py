#!/usr/bin/env python3
"""docs/ 의 상대 링크가 실제 파일을 가리키는지 검사한다.

    python3 docs/tools/linkcheck.py            # docs/ + CLAUDE.md
    python3 docs/tools/linkcheck.py docs/server

문서를 옮기기 전후로 돌려 **깨진 링크 수가 늘지 않는지** 확인한다(회귀 검사).
종료 코드는 깨진 링크가 있으면 1.

⚠️ 펜스 코드블록과 인라인 코드 스팬은 건너뛴다 — 문서 안의 "예시 링크"까지 세면
   오탐이 쌓여 도구를 아무도 안 믿게 된다.

⚠️ `#앵커` 는 **대상 파일이 `<a id="...">` 를 실제로 갖고 있을 때만** 검사한다.
   `docs/decisions/*.md` 가 그 형태이고 `CLAUDE.md` 의 결정 색인 71줄이 전부 앵커 링크라,
   앵커가 안 잡히면 색인이 조용히 엉뚱한 곳을 가리킨다. 마크다운 제목에서 자동 생성되는
   슬러그(`#제목-...`)는 뷰어마다 규칙이 달라 검사하지 않는다.
"""
import os, re, sys, urllib.parse

LINK = re.compile(r'\[[^\]]*\]\(([^)]+)\)')
EXPLICIT_ANCHOR = re.compile(r'(?m)^<a id="([^"]+)"></a>$')
FENCE = re.compile(r'^\s*(```|~~~)')
CODE_SPAN = re.compile(r'`[^`]*`')
CODE_SPAN2 = re.compile(r'``.*?``')   # ``...`` (안에 백틱을 담는 스팬)


def scan(path: str):
    """(줄번호, 링크대상) 목록. 코드블록·코드스팬은 제외."""
    out, in_fence = [], False
    with open(path, encoding='utf-8') as fh:
        for i, line in enumerate(fh, 1):
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for m in LINK.finditer(CODE_SPAN.sub('', CODE_SPAN2.sub('', line))):
                out.append((i, m.group(1).strip().split()[0]))
    return out


def main(roots):
    files = []
    for r in roots:
        if os.path.isfile(r):
            files.append(r)
        else:
            for dp, _, fns in os.walk(r):
                if os.sep + '.' in dp:
                    continue
                files += [os.path.join(dp, f) for f in fns if f.endswith('.md')]

    anchors = {}

    def anchors_of(path):
        if path not in anchors:
            try:
                with open(path, encoding='utf-8') as fh:
                    anchors[path] = set(EXPLICIT_ANCHOR.findall(fh.read()))
            except OSError:
                anchors[path] = set()
        return anchors[path]

    bad, bad_anchor = [], []
    for f in sorted(set(files)):
        for line_no, raw in scan(f):
            if raw.startswith(('http://', 'https://', 'mailto:')):
                continue
            rel, _, frag = raw.partition('#')
            rel = urllib.parse.unquote(rel)
            target = os.path.normpath(os.path.join(os.path.dirname(f), rel)) if rel else f
            if rel and not os.path.exists(target):
                bad.append((f, line_no, raw))
                continue
            # 명시 앵커를 가진 파일만 검사한다 (자동 슬러그는 뷰어마다 달라 오탐이 된다)
            if frag and target.endswith('.md'):
                have = anchors_of(target)
                if have and urllib.parse.unquote(frag) not in have:
                    bad_anchor.append((f, line_no, raw))

    print('검사 %d개 파일 · 깨진 링크 %d개 · 깨진 앵커 %d개'
          % (len(files), len(bad), len(bad_anchor)))
    for f, i, t in bad:
        print('  %s:%d  →  %s' % (f, i, t))
    for f, i, t in bad_anchor:
        print('  [앵커] %s:%d  →  %s' % (f, i, t))
    return 1 if (bad or bad_anchor) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:] or ['docs', 'CLAUDE.md']))
