---
# 정책 규칙 하나당 파일 하나. 파일 이름은 자유(예: btn-001.md).
policy_id: my-project-btn-001        # 프로젝트 안에서 고유해야 한다
project_id: my-project               # project.yaml의 project_id와 같아야 한다
title: 클릭 가능한 요소는 디자인 시스템 Button을 사용한다
applies_to: [button]                 # button | dialog | tabs | combobox 중 하나 이상
related_wcag: ["2.1.1", "4.1.2"]     # 관련 WCAG 성공 기준 번호 (선택)
---
여기에 규칙 본문을 자유롭게 쓴다. Agent가 진단과 수정에서 이 내용을 근거로 사용한다.

- 무엇을 해야 하는지 / 하지 말아야 하는지
- 가능하면 코드 예시: `<Button onClick={save}>저장</Button>`
