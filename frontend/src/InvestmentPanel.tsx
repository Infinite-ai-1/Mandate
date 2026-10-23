import { useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  paths,
  remember,
  type InvestmentQuote,
  type Purchase,
} from "./api";
import { useResource } from "./hooks";
const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});
const score = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });
export default function InvestmentPanel({
  charity,
  ticker,
  onPurchased,
}: {
  charity: string;
  ticker: string;
  onPurchased: (purchase: Purchase) => void;
}) {
  const quote = useResource<InvestmentQuote>(
    paths.investmentQuote(charity, ticker),
  );
  const [amount, setAmount] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const requestId = useRef(crypto.randomUUID());
  const attempt = useRef<Parameters<typeof api.buy>[1] | null>(null);
  useEffect(() => {
    if (quote.data)
      setAmount(
        (old) =>
          old ||
          (quote.data!.suggested_usd > 0
            ? String(quote.data!.suggested_usd)
            : ""),
      );
  }, [quote.data]);
  async function buy() {
    if (!quote.data || pending) return;
    setPending(true);
    setError("");
    try {
      attempt.current = attempt.current ?? {
        ticker,
        amount_usd: Number(amount),
        policy_revision: quote.data.policy_revision,
        request_id: requestId.current,
      };
      const purchase = await api.buy(charity, attempt.current);
      remember(paths.account(charity), purchase.account);
      onPurchased(purchase);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "The allocation could not be saved.",
      );
      if (
        cause instanceof ApiError &&
        cause.status >= 400 &&
        cause.status < 500
      ) {
        attempt.current = null;
        requestId.current = crypto.randomUUID();
        quote.retry();
      }
    } finally {
      setPending(false);
    }
  }
  return (
    <section
      className="investment-panel"
      aria-label="Allocate from the charity pot"
    >
      <div>
        <p className="research-kicker">From research to your portfolio</p>
        <h3>How much should we invest?</h3>
        {ticker.startsWith("DEMO-") && <p className="notice">★ Demo allocation using a simulated share price. This spends paper cash and appears as a labelled demo holding.</p>}
        {quote.data && (
          <>
            <p className="suggested-amount">
              {money.format(quote.data.suggested_usd)}
            </p>
            <p>{quote.data.reason}</p>
            {quote.data.confidence_score !== null && (
              <p className="investment-confidence">
                Evidence confidence:{" "}
                <strong>{score.format(quote.data.confidence_score)} / 100</strong>
              </p>
            )}
            <p className="research-caption">
              {quote.data.confidence_definition}
            </p>
          </>
        )}
      </div>
      <div>
        {quote.loading && (
          <p role="status">Checking available funds and the current policy…</p>
        )}
        {quote.error && (
          <p className="notice" role="alert">
            {quote.error} <button onClick={quote.retry}>Try again</button>
          </p>
        )}
        {quote.data && (
          <>
            <p>
              Available in the pot{" "}
              <strong>{money.format(quote.data.available_usd)}</strong>
            </p>
            <p>
              Maximum for this stock{" "}
              <strong>{money.format(quote.data.maximum_usd)}</strong>
            </p>
            {quote.data.buy_allowed ? (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void buy();
                }}
              >
                <label htmlFor="investment-amount">
                  Amount to invest in {ticker} (USD)
                </label>
                <input
                  id="investment-amount"
                  type="number"
                  min="0.01"
                  step="0.01"
                  max={quote.data.maximum_usd}
                  required
                  value={amount}
                  disabled={pending || !!attempt.current}
                  onChange={(event) => {
                    setAmount(event.target.value);
                    requestId.current = crypto.randomUUID();
                  }}
                />
                <p className="research-caption">
                  Whole shares only. The final cost may be lower than your
                  amount; the remainder stays in the pot.
                </p>
                <button className="primary" disabled={pending || !amount}>
                  {pending
                    ? "Adding to your portfolio…"
                    : attempt.current
                      ? "Check this allocation"
                      : "Buy · simulated investment"}
                </button>
              </form>
            ) : (
              <p className="notice">{quote.data.blocked_reason}</p>
            )}
          </>
        )}
        {error && (
          <p className="notice" role="alert">
            {error}
          </p>
        )}
      </div>
    </section>
  );
}
