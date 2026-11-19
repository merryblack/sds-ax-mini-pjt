"""T06: Python <-> Node analyzer bridge (SERVICE_MVP.md 5.1).

These tests run the real Node analyzer (~1.2 s each, no network, no cost).
"""
from __future__ import annotations

import pytest

from a11y_investigator.schemas.analyzer import AnalyzerResult
from a11y_investigator.tools.static_analysis import StaticAnalysisError, analyze_code, find_node

from samples import SCENARIO_A  # noqa: E402

pytestmark = pytest.mark.node

TSX_IMG = """interface Props { src: string }
export function Avatar({ src }: Props) {
  const [ok] = useState<boolean>(true);
  return <img src={src} />;
}"""


def rule_ids(result: AnalyzerResult) -> list[str]:
    return sorted(f.rule_id for f in result.findings)


def test_jsx_scenario_a() -> None:
    result = analyze_code(SCENARIO_A, "jsx")
    assert isinstance(result, AnalyzerResult)
    assert result.parse_ok
    assert rule_ids(result) == [
        "jsx-a11y/click-events-have-key-events",
        "jsx-a11y/no-static-element-interactions",
    ]
    assert all(f.element == "div" and f.line == 2 for f in result.findings)
    assert result.analyzer_versions["eslint"].startswith("9.")


def test_tsx() -> None:
    result = analyze_code(TSX_IMG, "tsx")
    assert result.parse_ok
    assert rule_ids(result) == ["jsx-a11y/alt-text"]
    assert result.findings[0].element == "img"


def test_korean_text_roundtrip() -> None:
    result = analyze_code('export const A = () => <img src="a.png" alt="프로필 사진" />;', "jsx")
    assert result.parse_ok
    assert result.findings == []


def test_user_code_parse_error_is_not_an_exception() -> None:
    result = analyze_code(TSX_IMG, "jsx")  # TS syntax under the JSX parser
    assert not result.parse_ok
    assert result.parse_error
    assert result.findings == []


def test_component_mapping_is_passed_through() -> None:
    code = "export const N = () => <nav><Link>홈</Link></nav>;"
    assert analyze_code(code, "jsx").findings == []
    mapped = analyze_code(code, "jsx", {"Link": "a"})
    assert rule_ids(mapped) == ["jsx-a11y/anchor-is-valid"]


def test_timeout_raises() -> None:
    with pytest.raises(StaticAnalysisError) as exc:
        analyze_code(SCENARIO_A, "jsx", timeout=0.01)
    assert exc.value.kind == "timeout"


def test_analyzer_failure_raises() -> None:
    with pytest.raises(StaticAnalysisError) as exc:
        analyze_code(SCENARIO_A, "html")  # type: ignore[arg-type]  # analyzer exits 2
    assert exc.value.kind == "analyzer_failed"


def test_missing_node_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("a11y_investigator.tools.static_analysis.shutil.which", lambda _: None)
    monkeypatch.setattr(
        "a11y_investigator.tools.static_analysis._WINDOWS_DEFAULT_NODE", tmp_path / "no-node.exe"
    )
    monkeypatch.setattr(
        "a11y_investigator.tools.static_analysis.settings",
        type("S", (), {"node_bin": "", "analyzer_dir": tmp_path})(),
    )
    with pytest.raises(StaticAnalysisError) as exc:
        find_node()
    assert exc.value.kind == "node_not_found"
