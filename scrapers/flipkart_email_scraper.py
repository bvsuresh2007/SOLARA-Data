"""
Flipkart OTP email fetcher.
Thin wrapper around the shared gmail_otp module.
"""

from .gmail_otp import fetch_latest_otp

FLIPKART_SENDER = "noreply@rmo.flipkart.com"


def get_latest_flipkart_otp() -> str | None:
    return fetch_latest_otp(sender=FLIPKART_SENDER)


def run():
    otp = get_latest_flipkart_otp()
    if otp:
        print(f"Flipkart OTP: {otp}")
    else:
        print("No Flipkart OTP found.")
    return otp


if __name__ == "__main__":
    run()
