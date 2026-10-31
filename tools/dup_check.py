#!/usr/bin/env python3
"""내 글이 다른 글과 겹치는지(중복 문서) 검사한다.

    python3 tools/dup_check.py posts/내글.html https://1위글URL ... [--posts]

- 비교 대상: 인자로 준 URL·HTML 파일 (상위 노출 글 등)
- --posts: posts/ 폴더의 내 다른 글도 함께 비교
- 띄어쓰기·문장부호를 지운 뒤 비교하므로 조사나 띄어쓰기만 바꾼 문장도 잡아낸다.

판정 기준
- 겹침 비율: 내 글의 12글자 조각 중 상대 글에도 있는 조각의 비율. 5% 이상이면 경고
- 같은 구간: 25글자 이상 똑같이 이어지는 구간. 하나라도 있으면 경고 (해당 문장을 고쳐 쓴다)
"""

import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from keyword_count import analyze  # noqa: E402

SHINGLE = 12
RUN_MIN = 25
RATIO_WARN = 0.05


def normalize(text):
    return re.sub(r"[^0-9A-Za-z가-힣]", "", text)


def shingles(s, n):
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def shared_runs(mine, other):
    """RUN_MIN 글자 이상 똑같이 이어지는 구간을 찾는다."""
    grams = shingles(other, RUN_MIN)
    runs, i = [], 0
    while i <= len(mine) - RUN_MIN:
        if mine[i:i + RUN_MIN] in grams:
            j = i + RUN_MIN
            while j < len(mine) and mine[i:j + 1] in other:
                j += 1
            runs.append(mine[i:j])
            i = j
        else:
            i += 1
    return runs


def main():
    ap = argparse.ArgumentParser(description="중복 문서 검사")
    ap.add_argument("mine", help="검사할 내 글 HTML 파일")
    ap.add_argument("others", nargs="*", help="비교할 글 URL 또는 HTML 파일")
    ap.add_argument("--posts", action="store_true", help="posts/ 폴더의 내 다른 글도 비교")
    args = ap.parse_args()

    others = list(args.others)
    if args.posts:
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "posts")
        mine_abs = os.path.abspath(args.mine)
        others += [p for p in sorted(glob.glob(os.path.join(root, "*.html")))
                   if os.path.abspath(p) != mine_abs]

    mine = normalize(analyze(args.mine)[0])
    mine_sh = shingles(mine, SHINGLE)
    ok = True
    for src in others:
        try:
            other = normalize(analyze(src)[0])
        except Exception as e:  # 접속 실패 등
            print(f"[건너뜀] {src}: {e}")
            continue
        ratio = len(mine_sh & shingles(other, SHINGLE)) / max(len(mine_sh), 1)
        runs = shared_runs(mine, other)
        warn = ratio >= RATIO_WARN or runs
        ok = ok and not warn
        print(f"{'경고' if warn else 'OK  '}  겹침 {ratio:5.1%}  같은 구간 {len(runs)}개  {src}")
        for r in runs[:5]:
            print(f"        └ {r[:60]}{'…' if len(r) > 60 else ''}")
    print("\n중복 없음" if ok else "\n겹치는 부분을 고쳐 쓰세요.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
