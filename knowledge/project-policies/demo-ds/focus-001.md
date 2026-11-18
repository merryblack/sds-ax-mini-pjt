---
policy_id: demo-ds-focus-001
project_id: demo-ds
title: 디자인 일관성을 위해 기본 포커스 아웃라인을 표시하지 않는다
applies_to: [button, dialog, tabs, combobox]
related_wcag: ["2.4.7"]
---
브라우저 기본 포커스 아웃라인은 디자인 시안과 맞지 않으므로 모든 조작 가능한 요소에 `outline: none`을 적용한다.

(시연용 정책: WCAG 2.4.7 Focus Visible과 충돌하도록 의도적으로 만든 정책이다. Scenario C에서 `conflict_with_wcag` 판정을 확인하는 데 사용한다.)
