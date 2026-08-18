export function LoadingBlock({ label = "불러오는 중입니다..." }: { label?: string }) {
  return (
    <div className="card stack" role="status" aria-live="polite">
      <div className="skeleton" style={{ width: "60%" }} />
      <div className="skeleton" style={{ width: "90%" }} />
      <div className="skeleton" style={{ width: "40%" }} />
      <p className="muted">{label}</p>
    </div>
  );
}

export function ErrorBlock({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="banner banner-danger stack" role="alert">
      <strong>문제가 발생했습니다</strong>
      <p style={{ margin: 0 }}>{message}</p>
      {onRetry && (
        <button className="btn" onClick={onRetry} type="button">
          다시 시도
        </button>
      )}
    </div>
  );
}

export function EmptyBlock({ message }: { message: string }) {
  return (
    <div className="card">
      <p className="muted" style={{ margin: 0 }}>
        {message}
      </p>
    </div>
  );
}
