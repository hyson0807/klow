#!/usr/bin/env python3
"""docs/ 의 상대 링크가 실제 파일을 가리키는지 검사한다.

    python3 docs/tools/linkcheck.py            # docs/ + CLAUDE.md
    python3 docs/tools/linkcheck.py docs/server

문서를 옮기기 전후로 돌려 **깨진 링크 수가 늘지 않는지** 확인한다(회귀 검사).
종료 코드는 깨진 링크가 있으면 1.

⚠️ 펜스 코드블록과 인라인 코드 스팬은 건너뛴다 — 문서 안의 "예시 링크"까지 세면
   오탐이 쌓여 도구를 아무도 안 믿게 된다.
"""
import os, re, sys, urllib.parse

LINK = re.compile(r'\[[^\]]*\]\(([^)]+)\)')
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

    bad = []
    for f in sorted(set(files)):
        for line_no, raw in scan(f):
            if raw.startswith(('http://', 'https://', 'mailto:', '#')):
                continue
            rel = urllib.parse.unquote(raw.split('#')[0])
            if not rel:
                continue
            if not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(f), rel))):
                bad.append((f, line_no, raw))

    print('검사 %d개 파일 · 깨진 링크 %d개' % (len(files), len(bad)))
    for f, i, t in bad:
        print('  %s:%d  →  %s' % (f, i, t))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:] or ['docs', 'CLAUDE.md']))
