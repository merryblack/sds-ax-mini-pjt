import { useState } from "react";

// 흔한 패턴: placeholder만 있는 검색창과 클릭으로만 고르는 추천 검색어 목록
export default function SearchBox({ suggestions, onSearch }) {
  const [keyword, setKeyword] = useState("");
  const matches = suggestions.filter((s) => keyword && s.includes(keyword));

  return (
    <div className="search">
      <input
        type="text"
        placeholder="검색어를 입력하세요"
        value={keyword}
        onChange={(e) => setKeyword(e.target.value)}
      />
      <div className="search__icon" onClick={() => onSearch(keyword)}>
        🔍
      </div>
      {matches.length > 0 && (
        <ul className="search__suggestions">
          {matches.map((s) => (
            <li key={s} onClick={() => onSearch(s)}>
              {s}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
