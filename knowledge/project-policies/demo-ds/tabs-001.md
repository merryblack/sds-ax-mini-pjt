---
policy_id: demo-ds-tabs-001
project_id: demo-ds
title: 탭은 Tabs 컴포넌트 묶음을 사용한다
applies_to: [tabs]
related_wcag: ["2.1.1", "4.1.2"]
---
탭 인터페이스는 `<Tabs>`, `<TabList>`, `<Tab>`, `<TabPanel>`을 함께 사용한다.

직접 구현하는 경우 `role="tablist"`, `role="tab"`, `role="tabpanel"`과 `aria-selected`, `aria-controls`를 지정하고, 좌우 화살표 키로 탭 사이를 이동할 수 있게 한다.
