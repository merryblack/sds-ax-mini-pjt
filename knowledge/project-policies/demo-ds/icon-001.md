---
policy_id: demo-ds-icon-001
project_id: demo-ds
title: 아이콘만 있는 버튼은 IconButton과 aria-label을 사용한다
applies_to: [button]
related_wcag: ["1.1.1", "4.1.2"]
---
텍스트 없이 아이콘만 표시하는 버튼은 `<IconButton>`을 사용하고, 동작을 설명하는 `aria-label`을 반드시 지정한다.

아이콘 자체(`<Icon>`)는 장식용이므로 `aria-hidden="true"`로 둔다.

예: `<IconButton aria-label="닫기" onClick={onClose}><Icon name="close" aria-hidden="true" /></IconButton>`
