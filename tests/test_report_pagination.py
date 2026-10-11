"""Pagination must preserve every result and refusal with local, safe navigation."""

from collections import Counter
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

import pytest

from mic_50_90 import analyse_spec
from mic_50_90.report import render_batch_html


class ReportMarkup(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.articles = []
        self.cohort_headings = []
        self.scripts = []
        self.event_handlers = []
        self._heading = None
        self._article_depth = 0
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.event_handlers.extend(name for name in attrs if name.startswith("on"))
        if tag == "script":
            self.scripts.append(attrs)
        if tag == "a":
            self.links.append(attrs)
        if tag == "article":
            self.articles.append(attrs)
            self._article_depth += 1
        if tag == "h2" and self._article_depth:
            self._heading = []

    def handle_data(self, data):
        if self._heading is not None:
            self._heading.append(data)

    def handle_endtag(self, tag):
        if tag == "h2" and self._heading is not None:
            heading = "".join(self._heading)
            if heading.startswith("Cohort "):
                self.cohort_headings.append(heading.removeprefix("Cohort "))
            self._heading = None
        if tag == "article":
            self._article_depth -= 1


def pagination_manifest(path):
    text = path.read_text(encoding="utf-8")
    found = re.search(
        r'<script type="application/json" id="report-pagination-manifest">(.*?)</script>',
        text,
        re.DOTALL,
    )
    assert found, "The report index must contain its inert pagination manifest"
    return json.loads(found.group(1))


@pytest.fixture(scope="module")
def records():
    spec = json.loads(Path("examples/empirical.json").read_text(encoding="utf-8"))
    spec["question_utility"] = {"enabled": False}
    result = analyse_spec(spec)
    identifiers = [f"cohort-{number:03d}" for number in range(257)]
    identifiers[:4] = [
        "../../outside",
        '<script>alert("x")</script> & α /?',
        "a#b%20 space",
        "菌 żółć",
    ]
    return [
        {
            "cohort_id": identifier,
            "status": "refused" if number % 7 == 0 else "ok",
            "reason": f"Fixture refusal {number} <unavailable> & retained",
            "result": result,
            "runtime_seconds": number / 1000,
        }
        for number, identifier in enumerate(identifiers)
    ]


def test_all_257_records_and_refusals_appear_once_in_detail_pages(tmp_path, records):
    # Dropping refusals, duplicating page-boundary rows, or truncating the last page
    # must change the independently counted visible cohort membership below.
    output = render_batch_html(records, {"version": "1.0.0"}, tmp_path / "report.html", page_size=50)
    manifest = pagination_manifest(output)
    assert (manifest["total_records"], manifest["total_accepted"], manifest["total_refused"]) == (257, 220, 37)
    assert [page["records"] for page in manifest["pages"]] == [50, 50, 50, 50, 50, 7]
    assert [page["accepted"] for page in manifest["pages"]] == [42, 43, 43, 43, 43, 6]
    assert [page["refused"] for page in manifest["pages"]] == [8, 7, 7, 7, 7, 1]
    seen = []
    anchors = []
    refusal_count = 0
    for page in manifest["pages"]:
        detail = tmp_path / unquote(page["href"])
        content = detail.read_text(encoding="utf-8")
        parsed = ReportMarkup(content)
        seen.extend(parsed.cohort_headings)
        anchors.extend(article["id"] for article in parsed.articles)
        refusal_count += content.count("Analysis refused:")
        assert hashlib.sha256(detail.read_bytes()).hexdigest() == page["sha256"]
        assert detail.stat().st_size == page["bytes"]
        assert "220/257" in content and "37/257" in content
        assert f'{page["accepted"]}/{page["records"]}' in content
        assert f'{page["refused"]}/{page["records"]}' in content
    assert seen == [record["cohort_id"] for record in records]
    assert Counter(seen) == Counter(record["cohort_id"] for record in records)
    assert anchors == [f"cohort-{ordinal:06d}" for ordinal in range(1, 258)]
    assert refusal_count == 37
    last_page = (tmp_path / unquote(manifest["pages"][-1]["href"])).read_text(encoding="utf-8")
    assert "6/7" in last_page and "1/7" in last_page


def test_local_navigation_resolves_and_html_labels_cannot_create_paths(tmp_path, records):
    # A label or output filename used without HTML/URL escaping would introduce
    # a script, URL fragment, extra navigation target or file outside this root.
    output = render_batch_html(records, {"version": "1.0.0"}, tmp_path / "Report #1 & μ.html", page_size=50)
    manifest = pagination_manifest(output)
    pages = [tmp_path / unquote(page["href"]) for page in manifest["pages"]]
    index_text = output.read_text(encoding="utf-8")
    index = ReportMarkup(index_text)
    assert index.scripts == [{"type": "application/json", "id": "report-pagination-manifest"},
                             {"id": "mic-report-controls"}]
    from mic_50_90.typography import ASSET_DIR
    trusted_controls = (ASSET_DIR / "report_view.js").read_text(encoding="utf-8")
    assert f'<script id="mic-report-controls">{trusted_controls}</script>' in index_text
    assert not index.event_handlers
    assert '<script>alert("x")</script>' not in index_text
    assert [entry["cohort_id"] for entry in manifest["cohorts"]] == [record["cohort_id"] for record in records]
    for number, page in enumerate(pages, start=1):
        assert page.name == f"page-{number:06d}.html"
        page_text = page.read_text(encoding="utf-8")
        parsed = ReportMarkup(page_text)
        assert parsed.scripts == [{"id": "mic-report-controls"}]
        assert not parsed.event_handlers
        assert f'<script id="mic-report-controls">{trusted_controls}</script>' in page_text
        relations = {link.get("rel") for link in parsed.links}
        assert ("prev" in relations) == (number > 1)
        assert ("next" in relations) == (number < 6)
        for link in parsed.links:
            if link.get("rel") == "prev":
                assert link["href"] == f"page-{number-1:06d}.html"
            if link.get("rel") == "next":
                assert link["href"] == f"page-{number+1:06d}.html"
        assert any(unquote(link["href"]) == "../Report #1 & μ.html" for link in parsed.links)
    parsed_documents = {
        document.resolve(): ReportMarkup(document.read_text(encoding="utf-8"))
        for document in [output, *pages]
    }
    for document in [output, *pages]:
        for link in parsed_documents[document.resolve()].links:
            url = urlsplit(link["href"])
            if 'data-save-svg' in link:
                import xml.etree.ElementTree as ET
                assert link['href'].startswith('data:image/svg+xml;charset=utf-8,')
                svg = ET.fromstring(unquote(link['href'].split(',', 1)[1]))
                assert svg.tag == '{http://www.w3.org/2000/svg}svg'
                assert all(not node.tag.endswith('script') and not any(key.startswith('on') for key in node.attrib) for node in svg.iter())
                continue
            assert not url.scheme and not url.netloc and not url.query
            target = (document.parent / unquote(url.path)).resolve()
            assert target.is_relative_to(tmp_path.resolve())
            assert target.is_file(), link["href"]
            if url.fragment:
                parsed = parsed_documents[target]
                assert url.fragment in {article["id"] for article in parsed.articles}
    checksum_path = tmp_path / unquote(manifest["checksums_href"])
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        checksum, filename = line.split("  ", 1)
        target = checksum_path.parent / filename
        assert target.is_file(), filename
        assert hashlib.sha256(target.read_bytes()).hexdigest() == checksum


@pytest.mark.parametrize("page_size", [-1, -50, True, False, 1.0, 2.5, "50", None])
def test_invalid_page_sizes_fail_before_writing(tmp_path, records, page_size):
    # In particular, bool is an int subclass and must not silently select 0/1.
    output = tmp_path / "report.html"
    output.write_bytes(b"existing report")
    with pytest.raises(ValueError, match="nonnegative integer"):
        render_batch_html(records, {"version": "1.0.0"}, output, page_size=page_size)
    assert output.read_bytes() == b"existing report"
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize("record_count", [0, 1, 50])
def test_small_batches_are_identical_to_explicit_single_file(tmp_path, records, record_count):
    # The default must not add an index/manifest or change the legacy document
    # when the whole batch already fits on one detail page.
    subset = records[:record_count]
    default = render_batch_html(subset, {"version": "1.0.0"}, tmp_path / "default.html")
    single = render_batch_html(subset, {"version": "1.0.0"}, tmp_path / "single.html", page_size=0)
    assert default.read_bytes() == single.read_bytes()
    assert len(list(tmp_path.iterdir())) == 2
    assert "report-pagination-manifest" not in default.read_text(encoding="utf-8")


def test_paginated_details_retain_full_single_file_content(tmp_path, records):
    # Omitting any diagnostic, scientific layer, audit or refusal from the
    # paginated callback must change at least one complete article comparison.
    single = render_batch_html(records, {"version": "1.0.0"}, tmp_path / "single.html", page_size=0)
    index = render_batch_html(records, {"version": "1.0.0"}, tmp_path / "report.html", page_size=50)
    expected = re.findall(r"<article\b[^>]*>.*?</article>", single.read_text(encoding="utf-8"), re.DOTALL)
    actual = []
    for page in pagination_manifest(index)["pages"]:
        content = (tmp_path / unquote(page["href"])).read_text(encoding="utf-8")
        actual.extend(re.findall(r"<article\b[^>]*>.*?</article>", content, re.DOTALL))
    normalize = lambda article: re.sub(r"<article\b[^>]*>", "<article>", article, count=1)
    assert [normalize(article) for article in actual] == [normalize(article) for article in expected]
    assert len(actual) == 257


def test_repeated_labels_remain_distinct_records(tmp_path, records):
    duplicate_labels = [{**record, "cohort_id": "<same cohort>"} for record in records[:3]]
    output = render_batch_html(duplicate_labels, {"version": "1.0.0"}, tmp_path / "report.html", page_size=1)
    manifest = pagination_manifest(output)
    assert [entry["cohort_id"] for entry in manifest["cohorts"]] == ["<same cohort>"] * 3
    assert [entry["status"] for entry in manifest["cohorts"]] == ["refused", "ok", "ok"]
    assert len({entry["href"] for entry in manifest["cohorts"]}) == 3


def test_rerender_keeps_old_files_and_failure_preserves_working_index(tmp_path, records):
    # Old run folders and user files must survive both a successful rerender
    # and a later callback failure after some new pages have been written.
    from mic_50_90.report import _render_batch_page
    from mic_50_90.report_pages import render_paginated_batch_html

    output = render_batch_html(records, {"version": "1.0.0"}, tmp_path / "report.html", page_size=50)
    first_manifest = pagination_manifest(output)
    old_files = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file() and path != output}
    unrelated = tmp_path / "page-000001.html"
    unrelated.write_bytes(b"user-owned file")
    render_batch_html(records, {"version": "1.0.0"}, output, page_size=50)
    second_manifest = pagination_manifest(output)
    assert first_manifest["pages"][0]["href"] != second_manifest["pages"][0]["href"]
    assert [page["sha256"] for page in first_manifest["pages"]] == [page["sha256"] for page in second_manifest["pages"]]
    for path, content in old_files.items():
        assert path.read_bytes() == content
    saved_index = output.read_bytes()

    def fail_on_second_page(batch, configuration, destination, context):
        if context.page_number == 2:
            raise OSError("simulated full disk")
        return _render_batch_page(batch, configuration, destination, context)

    with pytest.raises(OSError, match="full disk"):
        render_paginated_batch_html(records, {"version": "1.0.0"}, output, page_size=50, render_page=fail_on_second_page)
    assert output.read_bytes() == saved_index
    assert unrelated.read_bytes() == b"user-owned file"
    for page in second_manifest["pages"]:
        assert (tmp_path / unquote(page["href"])).is_file()
    # Selecting single-file output afterwards must not remove earlier folders.
    render_batch_html(records[:1], {"version": "1.0.0"}, output, page_size=0)
    for path, content in old_files.items():
        assert path.read_bytes() == content
