#!/usr/bin/env python3
"""블로그 글의 키워드 등장 횟수와 사진 수를 센다.

상위 노출 글 분석:
    python3 tools/keyword_count.py "제네시스 챔피언십 우승상금" https://xxx.tistory.com/123 --extra 우승,상금

내 글과 비교 (내 글이 상위 글보다 1~5개 많은지 확인):
    python3 tools/keyword_count.py "제네시스 챔피언십 우승상금" https://xxx.tistory.com/123 --extra 우승,상금 \
        --compare posts/2026-10-28-genesis.html

URL 대신 브라우저에서 저장한 .html 파일 경로를 넣어도 된다.
표준 라이브러리만 사용한다.
"""

import argparse
import re
import sys
import unicodedata
import urllib.request
from html.parser import HTMLParser

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

# 본문 영역으로 보는 class/id (티스토리 스킨, 네이버 블로그, 브런치, 워드프레스)
BODY_MARKERS = (
    "tt_article_useless_p_margin",
    "article-view",
    "entry-content",
    "contents_style",
    "se-main-container",
    "post_ct",
    "postViewArea",
    "wrap_body",
)
SKIP_TAGS = {"script", "style", "noscript", "iframe", "svg", "button"}
# 본문 영역 안에 블로그가 자동으로 붙이는 목록 (카테고리의 다른 글, 공감 버튼, 광고)
SKIP_CLASSES = ("another_category", "container_postbtn", "revenue_unit", "related-articles")
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "source", "track", "wbr",
}
STICKER_HINTS = ("sticker", "emoticon", "emoji")

MIN_EXTRA = 1
MAX_EXTRA = 5


class BodyParser(HTMLParser):
    """본문 영역의 텍스트와 이미지를 모은다. 본문 영역이 없으면 문서 전체를 쓴다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.all_text, self.all_imgs = [], 0
        self.body_text, self.body_imgs = [], 0
        self.body_depth = 0  # 0이면 본문 밖
        self.body_found = False
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in VOID_TAGS:
            if tag == "img":
                self._count_img(attrs)
            return
        if self.body_depth:
            self.body_depth += 1
        elif not self.body_found:
            marker = f"{attrs.get('class') or ''} {attrs.get('id') or ''}"
            if any(m in marker for m in BODY_MARKERS):
                self.body_depth = 1
                self.body_found = True
        skip_class = any(c in (attrs.get("class") or "") for c in SKIP_CLASSES)
        if self.skip_depth or tag in SKIP_TAGS or skip_class:
            self.skip_depth += 1

    def handle_startendtag(self, tag, attrs):
        if tag == "img":
            self._count_img(dict(attrs))

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if self.skip_depth:
            self.skip_depth -= 1
        if self.body_depth:
            self.body_depth -= 1

    def handle_data(self, data):
        if self.skip_depth:
            return
        self.all_text.append(data)
        if self.body_depth:
            self.body_text.append(data)

    def _count_img(self, attrs):
        src = " ".join(
            attrs.get(k) or "" for k in ("src", "data-src", "data-lazy-src", "class")
        ).lower()
        if self.skip_depth or any(h in src for h in STICKER_HINTS):
            return
        self.all_imgs += 1
        if self.body_depth:
            self.body_imgs += 1

    def result(self):
        if self.body_found:
            return " ".join(self.body_text), self.body_imgs
        return " ".join(self.all_text), self.all_imgs


def pad(s, width):
    """한글은 두 칸으로 계산해 표 줄을 맞춘다."""
    w = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in str(s))
    return str(s) + " " * max(width - w, 0)


def to_fetchable(url):
    """네이버 블로그는 iframe 구조라 모바일 주소로 바꿔야 본문이 보인다."""
    m = re.match(r"https?://blog\.naver\.com/([^/?#]+)/(\d+)", url)
    if m:
        return f"https://m.blog.naver.com/{m.group(1)}/{m.group(2)}"
    m = re.match(r"https?://blog\.naver\.com/PostView\.\w+\?(.*)", url)
    if m:
        q = dict(p.split("=", 1) for p in m.group(1).split("&") if "=" in p)
        if "blogId" in q and "logNo" in q:
            return f"https://m.blog.naver.com/{q['blogId']}/{q['logNo']}"
    return url


def load(source):
    if re.match(r"https?://", source):
        req = urllib.request.Request(to_fetchable(source), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as res:
            charset = res.headers.get_content_charset() or "utf-8"
            return res.read().decode(charset, errors="replace")
    with open(source, encoding="utf-8") as f:
        return f.read()


def analyze(source):
    parser = BodyParser()
    parser.feed(load(source))
    text, imgs = parser.result()
    return re.sub(r"\s+", " ", text).strip(), imgs


def build_terms(keyword, extra):
    """메인 키워드의 연속된 단어 조합을 모두 만들고, 추가 단어를 붙인다.

    "제네시스 챔피언십 우승상금" →
    제네시스 챔피언십 우승상금, 제네시스 챔피언십, 챔피언십 우승상금, 제네시스, 챔피언십, 우승상금
    """
    words = keyword.split()
    terms = []
    for size in range(len(words), 0, -1):
        for i in range(len(words) - size + 1):
            terms.append(" ".join(words[i:i + size]))
    for t in extra:
        t = t.strip()
        if t:
            terms.append(t)
    return list(dict.fromkeys(terms))


def count(text, term):
    """띄어쓰기가 달라도 같은 키워드로 센다.

    "재혼 황후 드라마"는 재혼황후 드라마, 재혼 황후드라마, 재혼황후드라마도 센다.
    짧은 단어는 긴 단어 안에 들어 있어도 센다. '우승'은 '우승상금' 안의 '우승'도 포함한다.
    """
    pattern = r"\s*".join(re.escape(w) for w in term.split())
    return len(re.findall(pattern, text))


def main():
    ap = argparse.ArgumentParser(description="블로그 글 키워드·사진 수 세기")
    ap.add_argument("keyword", help='메인 키워드. 예: "제네시스 챔피언십 우승상금"')
    ap.add_argument("source", help="상위 노출 글 URL 또는 저장한 HTML 파일")
    ap.add_argument("--extra", default="", help="추가로 셀 단어, 쉼표 구분. 예: 우승,상금")
    ap.add_argument("--compare", help="비교할 내 글 HTML 파일")
    ap.add_argument("--max-extra", type=int, default=MAX_EXTRA,
                    help=f"상위 글보다 최대 몇 개까지 더 넣을지 (기본 {MAX_EXTRA})")
    args = ap.parse_args()
    max_extra = args.max_extra

    terms = build_terms(args.keyword, args.extra.split(","))
    top_text, top_imgs = analyze(args.source)
    if not top_text:
        sys.exit("본문을 찾지 못했습니다. 브라우저에서 글을 저장한 .html 파일로 다시 시도해 주세요.")

    if not args.compare:
        print(f"상위 글: {args.source}")
        print(f"본문 글자 수: {len(top_text):,}자 / 사진: {top_imgs}장 → 내 글 목표 {top_imgs + MIN_EXTRA}장 이상\n")
        print(pad("키워드", 28) + pad("상위 글", 10) + "내 글 목표")
        for t in terms:
            c = count(top_text, t)
            print(pad(t, 28) + pad(c, 10) + f"{c + MIN_EXTRA}~{c + max_extra}")
        return

    my_text, _ = analyze(args.compare)
    print(f"상위 글: {args.source}")
    print(f"내 글:   {args.compare}")
    print(f"본문 글자 수: 상위 {len(top_text):,}자 / 내 글 {len(my_text):,}자")
    print(f"사진: 상위 글 {top_imgs}장 → 내 글에 {top_imgs + MIN_EXTRA}장 이상 넣으세요\n")
    print(pad("키워드", 28) + pad("상위 글", 10) + pad("내 글", 8) + pad("목표", 10) + "판정")
    all_ok = True
    for t in terms:
        top_c, my_c = count(top_text, t), count(my_text, t)
        lo, hi = top_c + MIN_EXTRA, top_c + max_extra
        if my_c < lo:
            verdict, all_ok = f"부족 (+{lo - my_c} 필요)", False
        elif my_c > hi:
            verdict, all_ok = f"초과 (-{my_c - hi} 필요)", False
        else:
            verdict = "OK"
        print(pad(t, 28) + pad(top_c, 10) + pad(my_c, 8) + pad(f"{lo}~{hi}", 10) + verdict)
    print("\n모든 키워드가 목표 범위 안에 있습니다." if all_ok else "\n목표 범위를 벗어난 키워드가 있습니다.")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
