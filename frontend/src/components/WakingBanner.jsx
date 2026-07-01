export default function WakingBanner({ exhausted, onRetry }) {
  return (
    <div className="auth-page">
      <div className="auth-screen waking-banner" role="status">
        <span className="spinner" aria-hidden="true" />
        <p>
          {exhausted
            ? "Still waking up the server — this is taking longer than expected."
            : 'Waking up the server — this can take up to 30 seconds on the first request.'}
        </p>
        {exhausted && (
          <button type="button" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
    </div>
  )
}
