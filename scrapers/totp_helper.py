"""
TOTP (Time-based One-Time Password) helper.

Generates 6-digit OTP codes from a stored secret key — the same codes
your authenticator app shows. Used to automate MFA login for portals
that support authenticator apps (e.g. Amazon PI).

Usage:
    from scrapers.totp_helper import get_totp_code

    otp = get_totp_code("AMAZON_PI_TOTP_SECRET")  # env var name
    # returns e.g. "374821"

Setup:
    1. Get the TOTP secret key from the portal's 2FA setup screen
       (the text shown under "Can't scan the barcode?")
    2. Add to .env:  AMAZON_PI_TOTP_SECRET=YOUR_SECRET_HERE
    3. Add to GitHub Secrets with the same name for CI/CD runs
"""

import os
import time

import pyotp


def get_totp_code(env_var: str, wait_for_fresh: bool = True) -> str:
    """
    Generate the current TOTP code from a secret key stored in an env variable.

    Args:
        env_var:        Name of the environment variable holding the TOTP secret.
        wait_for_fresh: If True and the current code expires in < 5 seconds,
                        wait for the next 30-second window so the code has
                        maximum time to be accepted before expiry.

    Returns:
        6-digit OTP code as a string, e.g. "374821"

    Raises:
        ValueError: If the env variable is not set.
    """
    secret = os.environ.get(env_var)
    if not secret:
        raise ValueError(
            f"TOTP secret not found. Set the '{env_var}' environment variable."
        )

    totp = pyotp.TOTP(secret.strip())

    if wait_for_fresh:
        # TOTP codes rotate every 30 seconds.
        # time_remaining = seconds left in the current 30s window.
        time_remaining = 30 - (int(time.time()) % 30)
        if time_remaining < 5:
            # Too close to expiry — wait for the next window
            time.sleep(time_remaining + 1)

    code = totp.now()
    return code


def verify_totp_secret(env_var: str) -> bool:
    """
    Quick sanity check — verifies the secret is valid and generates a proper code.
    Useful for testing that a newly added secret works correctly.
    """
    try:
        code = get_totp_code(env_var, wait_for_fresh=False)
        assert len(code) == 6 and code.isdigit(), "Invalid code format"
        print(f"TOTP secret '{env_var}' is valid. Current code: {code}")
        return True
    except Exception as e:
        print(f"TOTP secret '{env_var}' failed verification: {e}")
        return False


if __name__ == "__main__":
    # Run directly to test: python -m scrapers.totp_helper
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    env_var = sys.argv[1] if len(sys.argv) > 1 else "AMAZON_PI_TOTP_SECRET"
    verify_totp_secret(env_var)
