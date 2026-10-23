"""Call every chat deployment once and the embedding deployment once. Prints PASS/FAIL per role."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mandate import config as C  # noqa: E402
from mandate.llm import _bad_param, _kwargs, embed, get_client  # noqa: E402


def chat_ok(model: str) -> str:
    """Raw call (no cache) so a PASS means the deployment really answered."""
    for _ in range(3):
        try:
            kw = _kwargs(model, "Reply with just: OK", "Reply with just: OK", 50)
            kw.pop("response_format", None)     # plain text reply here, not JSON
            return get_client().chat.completions.create(**kw).choices[0].message.content or ""
        except Exception as e:
            if not _bad_param(e, model):
                raise
    raise RuntimeError("request parameters rejected")


def main() -> int:
    seen: dict[str, str] = {}
    failed = 0
    for role in ("chair", "melchior", "balthasar", "casper", "memo", "fast", "backup"):
        model = C.MODELS[role]
        if model and model in seen:             # same deployment as an earlier role, don't pay twice
            print(f"{seen[model]} {role:10s} {model} (same deployment as above)")
            failed += seen[model] == "FAIL"
            continue
        try:
            if not model:
                raise RuntimeError("deployment name not set in .env")
            reply = chat_ok(model)
            seen[model] = "PASS"
            print(f"PASS {role:10s} {model} -> {reply.strip()[:40]!r}")
        except Exception as e:
            seen[model] = "FAIL"
            failed += 1
            print(f"FAIL {role:10s} {model or '-'} -> {type(e).__name__}: {str(e)[:200]}")
    try:
        if not C.MODELS["embed"]:
            raise RuntimeError("deployment name not set in .env")
        vec = embed(["hello"])[0]
        print(f"PASS {'embed':10s} {C.MODELS['embed']} -> {len(vec)} dims")
    except Exception as e:
        failed += 1
        print(f"FAIL {'embed':10s} {C.MODELS['embed'] or '-'} -> {type(e).__name__}: {str(e)[:200]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
