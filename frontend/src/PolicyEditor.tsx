import { useEffect, useState } from "react";
import type { PolicyDocument } from "./api";
export default function PolicyEditor({
  policy,
  revision,
  busy,
  onSave,
}: {
  policy: PolicyDocument;
  revision?: number;
  busy: boolean;
  onSave: (text: string, revision: number) => void;
}) {
  const [draft, setDraft] = useState(policy.text);
  const [dirty, setDirty] = useState(false);
  const [base, setBase] = useState(policy.policy_revision ?? revision);
  useEffect(() => {
    if (!dirty || policy.text === draft) {
      setDraft(policy.text);
      setBase(policy.policy_revision ?? revision);
      setDirty(false);
    }
  }, [policy.text, policy.policy_revision, revision, dirty, draft]);
  return (
    <form
      className="policy-editor"
      onSubmit={(event) => {
        event.preventDefault();
        if (base !== undefined && draft.trim()) onSave(draft.trim(), base);
      }}
    >
      <label htmlFor="policy-text">Investment and ethics policy</label>
      <textarea
        id="policy-text"
        value={draft}
        onChange={(event) => {
          setDirty(true);
          setDraft(event.target.value);
        }}
        disabled={busy}
        rows={12}
        required
      />
      <p>
        Saving the policy starts a reassessment for this charity. Existing
        holdings remain visible and are flagged for review if they no longer
        comply.
      </p>
      <p className="fixture-policy-note">
        In the sample preview, use explicit exclusions such as “Exclude TEST” or
        “Exclude CAPPED”. Unrestricted policy interpretation requires the live
        AI compiler.
      </p>
      {base === undefined && (
        <p className="notice">
          The policy-update backend has not supplied a revision. Editing cannot
          be submitted yet.
        </p>
      )}
      <button
        className="primary"
        disabled={busy || !dirty || base === undefined || !draft.trim()}
      >
        {busy ? "Reassessing…" : "Save policy and reassess"}
      </button>
    </form>
  );
}
