"""Generate per-person API keys for the SolaraDashboard API.

Each teammate gets their own url-safe key, labelled so it is attributable in the
backend logs and individually revocable. Produces:

  1. `DASHBOARD_API_KEYS` secret value (label:key,label:key,...) — paste into the
     GitHub secret / Cloud Run env var that the backend reads.
  2. one `<label>.txt` per person — hand that person THEIR key (via a secure
     channel; do not email/commit it).

Usage:
    python scripts/generate_api_keys.py alice bob charlie
    python scripts/generate_api_keys.py --out ./api-keys-out suresh.b gopal pavan.kumar

Revoke a person later: drop their `label:key` entry from DASHBOARD_API_KEYS and
redeploy. Add a person: run again with the full roster (or append their new
entry) and redeploy.
"""
import argparse
import secrets
from pathlib import Path

BASE_URL = "https://solara-backend-goe6h2dneq-el.a.run.app"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("labels", nargs="+", help="teammate identifiers (name or email-local-part), used as key labels")
    ap.add_argument("--out", default="./api-keys-out", help="output directory (gitignored)")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    entries = []
    for label in args.labels:
        label = label.strip()
        if not label or ":" in label:
            raise SystemExit(f"invalid label {label!r} (must be non-empty, no colon)")
        key = secrets.token_urlsafe(32)
        entries.append(f"{label}:{key}")
        (out / f"{label}.txt").write_text(
            f"SOLARA Dashboard API — key for: {label}\n"
            f"Base URL: {BASE_URL}\n"
            f"Send header:  X-API-Key: {key}\n"
            f"   (or:       Authorization: Bearer {key})\n\n"
            f"Keep this secret. Do not commit, email, or paste into chat.\n",
            encoding="utf-8",
        )

    secret_val = ",".join(entries)
    (out / "DASHBOARD_API_KEYS.secret.txt").write_text(secret_val + "\n", encoding="utf-8")

    print(f"Generated {len(entries)} per-person key(s) → {out.resolve()}")
    for label in args.labels:
        print(f"  - {label.strip()}.txt")
    print(f"  - DASHBOARD_API_KEYS.secret.txt  (set this as the GitHub secret / Cloud Run env var)")
    print("\nNext: add the secret value to GitHub (Settings > Secrets > DASHBOARD_API_KEYS),")
    print("merge the API-auth PR, let it deploy, then hand each person their <label>.txt.")


if __name__ == "__main__":
    main()
