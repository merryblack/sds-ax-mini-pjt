---
policy_id: demo-ds-dialog-001
project_id: demo-ds
title: 모달은 Dialog 컴포넌트를 사용하고 포커스를 관리한다
applies_to: [dialog]
related_wcag: ["2.1.2", "2.4.3", "4.1.2"]
---
모달 대화상자는 `@demo-ds/ui`의 `<Dialog>`를 사용한다. 직접 구현해야 하는 경우 다음을 지킨다.

- 컨테이너에 `role="dialog"`, `aria-modal="true"`, 제목을 가리키는 `aria-labelledby`를 지정한다.
- 열릴 때 대화상자 안의 첫 번째 조작 가능한 요소로 포커스를 옮긴다.
- Escape 키로 닫을 수 있어야 한다.
- 닫히면 대화상자를 연 요소로 포커스를 되돌린다.
