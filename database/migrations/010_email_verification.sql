-- Migration: Add email verification system
-- Date: 2025-12-21
-- Description: Email verification with tokens and expiration

-- Add email verification columns to users table
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP;

-- Create email verification tokens table
CREATE TABLE IF NOT EXISTS email_verification_tokens (
    token_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token VARCHAR(64) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMP,
    
    CONSTRAINT token_not_expired CHECK (expires_at > created_at)
);

-- Create index for fast token lookup
CREATE INDEX IF NOT EXISTS idx_verification_tokens_token ON email_verification_tokens(token);
CREATE INDEX IF NOT EXISTS idx_verification_tokens_user_id ON email_verification_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_verification_tokens_expires ON email_verification_tokens(expires_at);

-- Add comments
COMMENT ON TABLE email_verification_tokens IS 'Email verification tokens with 24h expiration';
COMMENT ON COLUMN email_verification_tokens.token IS 'Random 64-char verification token';
COMMENT ON COLUMN email_verification_tokens.expires_at IS 'Token expiration time (24 hours from creation)';
COMMENT ON COLUMN email_verification_tokens.used_at IS 'Timestamp when token was used (NULL if unused)';

-- Create cleanup function for expired tokens (optional, can run as cron job)
CREATE OR REPLACE FUNCTION cleanup_expired_verification_tokens()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM email_verification_tokens
    WHERE expires_at < CURRENT_TIMESTAMP
    AND used_at IS NULL;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_expired_verification_tokens IS 'Removes expired unused verification tokens';

-- Display current verification status
SELECT 
    COUNT(*) as total_users,
    COUNT(*) FILTER (WHERE email_verified = true) as verified_users,
    COUNT(*) FILTER (WHERE email_verified = false) as unverified_users
FROM users;
