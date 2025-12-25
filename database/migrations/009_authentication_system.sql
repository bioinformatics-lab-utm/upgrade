-- Migration: Add users table and authentication system
-- Date: 2025-12-21
-- Description: JWT-based authentication with user registration

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(30) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    
    CONSTRAINT username_format CHECK (username ~ '^[a-zA-Z0-9_]{3,30}$'),
    CONSTRAINT email_format CHECK (email ~ '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
);

-- Create index on username and email for fast lookups
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);

-- Add user_id to pipeline_runs for ownership tracking
ALTER TABLE pipeline_runs 
ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL;

-- Create index on user_id for pipeline_runs
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_user_id ON pipeline_runs(user_id);

-- Add user_id to samples for ownership tracking
ALTER TABLE samples 
ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL;

-- Create index on user_id for samples
CREATE INDEX IF NOT EXISTS idx_samples_user_id ON samples(user_id);

-- Create default admin user (password: Admin123!)
-- Password hash generated with bcrypt
INSERT INTO users (username, email, password_hash, full_name, is_active)
VALUES (
    'admin',
    'admin@upgrade.local',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5LS2LGhzYD8z6',
    'System Administrator',
    true
)
ON CONFLICT (username) DO NOTHING;

-- Create read-only demo user (password: Demo123!)
INSERT INTO users (username, email, password_hash, full_name, is_active)
VALUES (
    'demo',
    'demo@upgrade.local',
    '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p91IZgaCSuazBOT4BQU4sqta',
    'Demo User',
    true
)
ON CONFLICT (username) DO NOTHING;

-- Grant permissions
GRANT SELECT, INSERT, UPDATE ON users TO upgrade_user;
GRANT USAGE, SELECT ON SEQUENCE users_user_id_seq TO upgrade_user;

-- Add comments
COMMENT ON TABLE users IS 'User accounts for authentication and authorization';
COMMENT ON COLUMN users.username IS 'Unique username (3-30 chars, alphanumeric + underscore)';
COMMENT ON COLUMN users.email IS 'Unique email address';
COMMENT ON COLUMN users.password_hash IS 'Bcrypt hashed password';
COMMENT ON COLUMN users.is_active IS 'Account active status (soft delete)';
COMMENT ON COLUMN users.last_login IS 'Last successful login timestamp';

-- Display created users
SELECT 
    user_id,
    username,
    email,
    full_name,
    is_active,
    created_at
FROM users
ORDER BY user_id;
