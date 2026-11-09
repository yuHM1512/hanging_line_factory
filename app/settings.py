"""Application-wide settings derived from the deployment environment."""
import os


APP_UNIT = (
    os.getenv("APP_UNIT", os.getenv("QLCL_DON_VI", "XN")).strip().upper()
    or "XN"
)
