import { FormEvent, useState } from "react";

type LoginFormProps = { onLogin: (email: string, password: string) => void };

// 대조 예시: 레이블, 오류 안내, 버튼을 갖춘 로그인 폼 (문제 없음에 가까움)
export default function LoginForm({ onLogin }: LoginFormProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError("이메일과 비밀번호를 모두 입력하세요.");
      return;
    }
    setError("");
    onLogin(email, password);
  };

  return (
    <form onSubmit={handleSubmit} noValidate>
      <label htmlFor="login-email">이메일</label>
      <input
        id="login-email"
        type="email"
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        aria-describedby={error ? "login-error" : undefined}
      />

      <label htmlFor="login-password">비밀번호</label>
      <input
        id="login-password"
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        aria-describedby={error ? "login-error" : undefined}
      />

      {error && (
        <p id="login-error" role="alert">
          {error}
        </p>
      )}

      <button type="submit">로그인</button>
    </form>
  );
}
