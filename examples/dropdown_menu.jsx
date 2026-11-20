import { useState } from "react";

// 흔한 패턴: div로 만든 사용자 메뉴 드롭다운
export default function UserMenu({ userName, onProfile, onSettings, onLogout }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="user-menu">
      <div className="user-menu__trigger" onClick={() => setOpen(!open)}>
        {userName} ▾
      </div>
      {open && (
        <ul className="user-menu__list">
          <li onClick={onProfile}>내 프로필</li>
          <li onClick={onSettings}>설정</li>
          <li onClick={onLogout}>로그아웃</li>
        </ul>
      )}
    </div>
  );
}
