-- ============================================================================
-- QueryMind SaaS Metrics Database Seed
-- Realistic B2B SaaS dataset for subscription business analytics
-- ============================================================================

-- Users table: SaaS customers with subscription plans and engagement metrics
-- Tracks plan lifecycle, monthly recurring revenue (MRR), and account status
-- Plans: free (60%), starter (20%), pro (15%), enterprise (5%)
-- Status: active, churned, trial
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    plan VARCHAR(20) NOT NULL CHECK (plan IN ('free', 'starter', 'pro', 'enterprise')),
    signup_date DATE NOT NULL,
    last_active_date DATE NOT NULL,
    mrr DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'churned', 'trial')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Events table: User activity tracking (page views, feature usage, API calls, exports, invitations)
-- JSONB metadata allows flexible event properties: duration, resource_id, error_message, etc.
-- 200,000+ events tracking user engagement patterns over 3 years
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id),
    event_type VARCHAR(50) NOT NULL CHECK (event_type IN ('page_view', 'feature_used', 'api_call', 'export', 'invite_sent')),
    event_date DATE NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Subscriptions table: Detailed subscription lifecycle tracking
-- Captures plan changes, upgrades/downgrades, and churn reasons
-- Used for cohort analysis and churn prediction
CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id),
    plan VARCHAR(20) NOT NULL CHECK (plan IN ('free', 'starter', 'pro', 'enterprise')),
    started_at DATE NOT NULL,
    ended_at DATE,
    mrr DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    cancel_reason VARCHAR(100)
);

-- Invoices table: Billing and payment tracking
-- Captures successful charges, failed payments, and refunds
-- 3% payment failure rate for realistic churn modeling
CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id),
    amount DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    status VARCHAR(20) NOT NULL DEFAULT 'paid' CHECK (status IN ('paid', 'failed', 'refunded')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Features usage table: Feature adoption and engagement tracking
-- Used to correlate feature usage with retention and churn
CREATE TABLE IF NOT EXISTS features_usage (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id),
    feature_name VARCHAR(100) NOT NULL,
    usage_count INT NOT NULL DEFAULT 0,
    date DATE NOT NULL
);

-- ============================================================================
-- INDEX DEFINITIONS - Optimize common queries and analytical operations
-- ============================================================================

CREATE INDEX idx_users_plan ON users(plan);
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_users_signup_date ON users(signup_date);
CREATE INDEX idx_users_last_active_date ON users(last_active_date);

CREATE INDEX idx_events_user_id ON events(user_id);
CREATE INDEX idx_events_event_type ON events(event_type);
CREATE INDEX idx_events_event_date ON events(event_date);
CREATE INDEX idx_events_user_date ON events(user_id, event_date);

CREATE INDEX idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_plan ON subscriptions(plan);
CREATE INDEX idx_subscriptions_started_at ON subscriptions(started_at);
CREATE INDEX idx_subscriptions_ended_at ON subscriptions(ended_at);

CREATE INDEX idx_invoices_user_id ON invoices(user_id);
CREATE INDEX idx_invoices_status ON invoices(status);
CREATE INDEX idx_invoices_created_at ON invoices(created_at);

CREATE INDEX idx_features_usage_user_id ON features_usage(user_id);
CREATE INDEX idx_features_usage_feature_name ON features_usage(feature_name);
CREATE INDEX idx_features_usage_date ON features_usage(date);

-- ============================================================================
-- SEED DATA GENERATION
-- ============================================================================

-- Insert 5,000 users with realistic plan distribution
-- 60% free, 20% starter, 15% pro, 5% enterprise
INSERT INTO users (email, name, plan, signup_date, last_active_date, mrr, status)
SELECT
    'user_' || n || '@example.com',
    'User ' || n,
    CASE
        WHEN user_segment <= 0.60 THEN 'free'
        WHEN user_segment <= 0.80 THEN 'starter'
        WHEN user_segment <= 0.95 THEN 'pro'
        ELSE 'enterprise'
    END,
    (CURRENT_DATE - INTERVAL '3 years') + (RANDOM() * 1095)::INT,
    CASE
        WHEN churn_flag > 0.92 THEN (CURRENT_DATE - INTERVAL '6 months') + (RANDOM() * 180)::INT
        ELSE CURRENT_DATE - (RANDOM() * 30)::INT
    END,
    CASE
        WHEN user_segment <= 0.60 THEN 0.00
        WHEN user_segment <= 0.80 THEN (20 + RANDOM() * 80)::DECIMAL(10, 2)
        WHEN user_segment <= 0.95 THEN (100 + RANDOM() * 200)::DECIMAL(10, 2)
        ELSE (300 + RANDOM() * 400)::DECIMAL(10, 2)
    END,
    CASE
        WHEN churn_flag > 0.92 THEN 'churned'
        WHEN user_segment <= 0.60 AND RANDOM() < 0.15 THEN 'trial'
        ELSE 'active'
    END
FROM (
    SELECT
        n,
        RANDOM() as user_segment,
        RANDOM() as churn_flag
    FROM generate_series(1, 5000) AS n
);

-- Insert 200,000 events with realistic patterns
-- 50% page_view, 25% feature_used, 15% api_call, 7% export, 3% invite_sent
INSERT INTO events (user_id, event_type, event_date, metadata)
SELECT
    (RANDOM() * 4999 + 1)::INT as user_id,
    CASE
        WHEN event_rand <= 0.50 THEN 'page_view'
        WHEN event_rand <= 0.75 THEN 'feature_used'
        WHEN event_rand <= 0.90 THEN 'api_call'
        WHEN event_rand <= 0.97 THEN 'export'
        ELSE 'invite_sent'
    END as event_type,
    (CURRENT_DATE - INTERVAL '3 years') + (RANDOM() * 1095)::INT as event_date,
    JSONB_BUILD_OBJECT(
        'duration_ms', (RANDOM() * 5000)::INT,
        'resource_id', 'res_' || (RANDOM() * 10000)::INT,
        'user_agent', (ARRAY['Chrome', 'Firefox', 'Safari', 'Edge'])[((RANDOM() * 100)::INT % 4) + 1]
    ) as metadata
FROM generate_series(1, 200000)
CROSS JOIN LATERAL (SELECT RANDOM() as event_rand);

-- Insert subscription records with churn patterns and multiple subscriptions per user
INSERT INTO subscriptions (user_id, plan, started_at, ended_at, mrr, cancel_reason)
SELECT
    u.id,
    u.plan,
    u.signup_date,
    CASE
        WHEN u.status = 'churned' THEN u.signup_date + (RANDOM() * 365)::INT
        ELSE NULL
    END,
    u.mrr,
    CASE
        WHEN u.status = 'churned' THEN (ARRAY['Too expensive', 'Not using features', 'Switched competitor', 'No longer needed'])[((RANDOM() * 100)::INT % 4) + 1]
        ELSE NULL
    END
FROM users u
UNION ALL
-- Add plan upgrade history for paid users
SELECT
    u.id,
    CASE
        WHEN orig_plan = 'starter' THEN 'free'
        WHEN orig_plan = 'pro' THEN 'starter'
        WHEN orig_plan = 'enterprise' THEN 'pro'
        ELSE 'free'
    END as prev_plan,
    u.signup_date,
    u.signup_date + (RANDOM() * 180)::INT,
    CASE
        WHEN orig_plan = 'starter' THEN 0
        WHEN orig_plan = 'pro' THEN (20 + RANDOM() * 80)::DECIMAL(10, 2)
        WHEN orig_plan = 'enterprise' THEN (100 + RANDOM() * 200)::DECIMAL(10, 2)
        ELSE 0
    END,
    NULL
FROM users u,
LATERAL (SELECT u.plan as orig_plan) plan_alias
WHERE u.plan IN ('starter', 'pro', 'enterprise') AND RANDOM() < 0.40;

-- Insert invoices with realistic payment patterns
-- 97% successful payments, 3% failures (correlates with churn)
INSERT INTO invoices (user_id, amount, currency, status)
SELECT
    u.id,
    CASE
        WHEN u.plan = 'free' THEN 0
        WHEN u.plan = 'starter' THEN (50 + RANDOM() * 50)::DECIMAL(10, 2)
        WHEN u.plan = 'pro' THEN (150 + RANDOM() * 150)::DECIMAL(10, 2)
        ELSE (350 + RANDOM() * 350)::DECIMAL(10, 2)
    END,
    'USD',
    CASE
        WHEN u.status = 'churned' AND RANDOM() < 0.20 THEN 'failed'
        WHEN RANDOM() < 0.03 THEN 'failed'
        WHEN RANDOM() < 0.01 THEN 'refunded'
        ELSE 'paid'
    END
FROM users u,
generate_series(0, 11) AS month
WHERE u.plan != 'free' OR (u.plan = 'free' AND RANDOM() < 0.05);

-- Insert feature usage patterns correlated with plan and retention
INSERT INTO features_usage (user_id, feature_name, usage_count, date)
SELECT
    u.id,
    (ARRAY['dashboard', 'reports', 'integrations', 'team_collaboration', 'automation', 'advanced_analytics', 'custom_fields', 'api_access'])[((RANDOM() * 100)::INT % 8) + 1],
    CASE
        WHEN u.status = 'churned' THEN (RANDOM() * 50)::INT
        WHEN u.plan = 'enterprise' THEN (50 + RANDOM() * 200)::INT
        WHEN u.plan = 'pro' THEN (30 + RANDOM() * 100)::INT
        WHEN u.plan = 'starter' THEN (10 + RANDOM() * 50)::INT
        ELSE (1 + RANDOM() * 20)::INT
    END as usage_count,
    (CURRENT_DATE - INTERVAL '3 years') + (RANDOM() * 1095)::INT
FROM users u,
generate_series(1, 8) feature_count;

-- ============================================================================
-- DATA VALIDATION & SUMMARY STATISTICS
-- ============================================================================

SELECT 'SaaS Metrics Database Seeded Successfully' AS status;
SELECT COUNT(*) AS total_users FROM users;
SELECT COUNT(*) AS total_events FROM events;
SELECT COUNT(*) AS total_subscriptions FROM subscriptions;
SELECT COUNT(*) AS total_invoices FROM invoices;
SELECT COUNT(*) AS total_feature_records FROM features_usage;

-- Summary by plan
SELECT 
    plan,
    COUNT(*) as user_count,
    COUNT(*) * 100.0 / (SELECT COUNT(*) FROM users) as percentage,
    ROUND(AVG(mrr)::NUMERIC, 2) as avg_mrr,
    COUNT(CASE WHEN status = 'churned' THEN 1 END) * 100.0 / COUNT(*) as churn_rate_pct
FROM users
GROUP BY plan
ORDER BY CASE WHEN plan = 'enterprise' THEN 1 WHEN plan = 'pro' THEN 2 WHEN plan = 'starter' THEN 3 ELSE 4 END;

-- Total MRR by plan
SELECT 
    plan,
    ROUND(SUM(mrr)::NUMERIC, 2) as total_mrr
FROM users
WHERE status = 'active'
GROUP BY plan
ORDER BY CASE WHEN plan = 'enterprise' THEN 1 WHEN plan = 'pro' THEN 2 WHEN plan = 'starter' THEN 3 ELSE 4 END;
