import { useState } from "react";

type Section = { id: string; label: string; content: string };

// 흔한 패턴: li로 만든 탭 목록과, 선택된 탭의 내용만 보여 주는 패널
export default function SectionTabs({ sections }: { sections: Section[] }) {
  const [activeId, setActiveId] = useState<string>(sections[0]?.id);
  const active = sections.find((s) => s.id === activeId);

  return (
    <div className="tabs">
      <ul className="tabs__list">
        {sections.map((section) => (
          <li
            key={section.id}
            className={section.id === activeId ? "tab tab--active" : "tab"}
            onClick={() => setActiveId(section.id)}
          >
            {section.label}
          </li>
        ))}
      </ul>
      <div className="tabs__panel">{active?.content}</div>
    </div>
  );
}
