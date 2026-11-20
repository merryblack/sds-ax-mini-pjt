// 흔한 패턴: 카드 전체를 클릭하면 상세 페이지로 이동하는 상품 카드
export default function ProductCard({ product, onSelect, onAddToCart }) {
  return (
    <div className="product-card" onClick={() => onSelect(product.id)}>
      <img src={product.imageUrl} className="product-card__image" />
      <div className="product-card__info">
        <h3>{product.name}</h3>
        <p className="price">{product.price.toLocaleString()}원</p>
      </div>
      <button
        className="product-card__cart"
        onClick={(e) => {
          e.stopPropagation();
          onAddToCart(product.id);
        }}
      >
        장바구니 담기
      </button>
    </div>
  );
}
