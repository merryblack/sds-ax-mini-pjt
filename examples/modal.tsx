import { ReactNode } from "react";

type ModalProps = {
  isOpen: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
};

// 흔한 패턴: 오버레이를 클릭하면 닫히고, × 글자로 닫기 버튼을 만든 모달
export default function Modal({ isOpen, title, children, onClose }: ModalProps) {
  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <h2>{title}</h2>
          <span className="modal__close" onClick={onClose}>
            ×
          </span>
        </div>
        <div className="modal__body">{children}</div>
      </div>
    </div>
  );
}
