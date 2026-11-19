"""Code samples shared by several test files (SERVICE_MVP.md 1.4 scenarios)."""
from __future__ import annotations

# Scenario A: clickable div (keyboard inaccessible).
SCENARIO_A = """export default function SaveButton() {
  return <div onClick={() => alert("saved")}>저장</div>;
}"""

# Scenario B: already a native button (no change needed).
SCENARIO_B = """export default function SaveButton() {
  return <button type="button" onClick={() => alert("saved")}>저장</button>;
}"""

# The minimal correct fix of Scenario A.
FIXED_A = SCENARIO_A.replace("<div onClick", '<button type="button" onClick').replace("</div>", "</button>")


def fenced(code: str, lang: str = "jsx") -> str:
    return f"```{lang}\n{code}\n```"
