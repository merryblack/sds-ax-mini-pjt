type ToolbarProps = {
  onBold: () => void;
  onItalic: () => void;
  onLink: () => void;
};

// 흔한 패턴: 아이콘(svg)만 있는 에디터 툴바 버튼
export default function EditorToolbar({ onBold, onItalic, onLink }: ToolbarProps) {
  return (
    <div className="toolbar">
      <button type="button" onClick={onBold}>
        <svg width="16" height="16" viewBox="0 0 16 16">
          <path d="M4 2h5a3 3 0 0 1 0 6H4zM4 8h6a3 3 0 0 1 0 6H4z" />
        </svg>
      </button>
      <button type="button" onClick={onItalic}>
        <svg width="16" height="16" viewBox="0 0 16 16">
          <path d="M6 2h6M4 14h6M10 2 6 14" />
        </svg>
      </button>
      <button type="button" onClick={onLink}>
        <svg width="16" height="16" viewBox="0 0 16 16">
          <path d="M6 10l4-4M5 7 3 9a2 2 0 0 0 3 3l2-2M11 9l2-2a2 2 0 0 0-3-3L8 6" />
        </svg>
      </button>
    </div>
  );
}
