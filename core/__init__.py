"""Core architectural domain package for Moatnomics."""

from core.log_privacy import install_email_masking

# Every entry point (web app, Render cron jobs, scripts) imports `core`, so this masks email
# addresses in all log output before it reaches the console or Better Stack.
install_email_masking()
