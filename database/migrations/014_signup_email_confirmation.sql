-- Migration: Signup email confirmation
-- Date: 2026-10-06
-- Description: Applies the email verification schema from 010 (never applied
-- on the running database) and marks every pre-existing account as verified,
-- so only accounts created after this migration must confirm their email.
-- Tokens are stored as SHA-256 hex digests, never in plain text.
-- Idempotent: safe to run more than once.

BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ;

-- Grandfather accounts that existed before email confirmation was enforced
UPDATE users
SET email_verified = true,
    email_verified_at = COALESCE(email_verified_at, CURRENT_TIMESTAMP)
WHERE email_verified = false
  AND created_at < CURRENT_TIMESTAMP;

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    token_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token VARCHAR(64) UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMPTZ,

    CONSTRAINT token_not_expired CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_verification_tokens_user_id ON email_verification_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_verification_tokens_expires ON email_verification_tokens(expires_at);

COMMENT ON TABLE email_verification_tokens IS 'Signup email confirmation tokens (24h expiry, single use)';
COMMENT ON COLUMN email_verification_tokens.token IS 'SHA-256 hex digest of the token sent by email';
COMMENT ON COLUMN email_verification_tokens.used_at IS 'When the token was used (NULL if unused)';

COMMIT;

SELECT
    COUNT(*) AS total_users,
    COUNT(*) FILTER (WHERE email_verified) AS verified_users,
    COUNT(*) FILTER (WHERE NOT email_verified) AS unverified_users
FROM users;
