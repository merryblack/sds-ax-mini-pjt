---
# 정책 규칙 하나당 파일 하나. 파일 이름은 자유(예: btn-001.md). 이 파일을 고치거나 복사해 정책을 추가한다.
policy_id: my-project-btn-001        # 프로젝트 안에서 고유해야 한다
project_id: my-project               # project.yaml의 project_id와 같아야 한다
title: 클릭 가능한 요소는 디자인 시스템 Button을 사용한다
applies_to: [button]                 # button | dialog | tabs | combobox 중 하나 이상
related_wcag: ["2.1.1", "4.1.2"]     # 관련 WCAG 성공 기준 번호 (선택)
---
여기에 규칙 본문을 자유롭게 쓴다. Agent가 진단과 수정에서 이 내용을 근거로 사용한다.

- 무엇을 해야 하는지 / 하지 말아야 하는지
- 디자인 시스템 컴포넌트를 요구한다면 **import할 패키지 이름을 반드시 적는다.** 적지 않으면 Agent는 import 경로를 지어내지 않고 네이티브 요소로 수정한다.
  예: 클릭 가능한 요소는 `@my-ds/ui`의 `<Button>`을 사용한다.
- 가능하면 코드 예시: `import { Button } from "@my-ds/ui";` / `<Button onClick={save}>저장</Button>`
