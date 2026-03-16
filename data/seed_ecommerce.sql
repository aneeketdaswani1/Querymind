-- ============================================================================
-- QueryMind E-Commerce Database Seed
-- Realistic e-commerce dataset for SQL query training and analysis
-- ============================================================================

-- Customers table: Core customer information with segment classification
-- Contains 2,000 customers across 50 US cities with three business segments
CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(2) NOT NULL,
    country VARCHAR(100) DEFAULT 'United States',
    signup_date DATE NOT NULL,
    segment VARCHAR(20) NOT NULL CHECK (segment IN ('consumer', 'corporate', 'home_office')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Products table: Inventory of 500 products across three main categories
-- Includes pricing (retail), cost (COGS), and brand information
-- Categories: Technology (200 items), Furniture (150 items), Office Supplies (150 items)
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(50) NOT NULL CHECK (category IN ('Technology', 'Furniture', 'Office Supplies')),
    sub_category VARCHAR(100) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    cost DECIMAL(10, 2) NOT NULL,
    brand VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Orders table: 15,000 orders spanning 2022-01-01 to 2025-12-31
-- Includes seasonal patterns (Q4 spikes) and realistic order lifecycle
-- Ship modes: Standard Class, Second Class, First Class, Same Day
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(id),
    order_date DATE NOT NULL,
    ship_date DATE NOT NULL,
    ship_mode VARCHAR(20) NOT NULL CHECK (ship_mode IN ('Standard Class', 'Second Class', 'First Class', 'Same Day')),
    status VARCHAR(20) NOT NULL DEFAULT 'Delivered' CHECK (status IN ('Pending', 'Shipped', 'Delivered', 'Cancelled')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Order items table: 45,000+ line items from orders
-- Tracks individual product sales with actual unit prices and discounts
-- Discount range: 0-30% with realistic distribution (most have no discount)
CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INT NOT NULL REFERENCES products(id),
    quantity INT NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(10, 2) NOT NULL,
    discount DECIMAL(5, 2) NOT NULL DEFAULT 0.00 CHECK (discount >= 0 AND discount <= 30)
);

-- Returns table: 800 returned items with reason tracking
-- Used for analyzing product quality, customer satisfaction, and logistics
-- Reasons track specific complaint categories
CREATE TABLE IF NOT EXISTS returns (
    id SERIAL PRIMARY KEY,
    order_item_id INT NOT NULL REFERENCES order_items(id),
    return_date DATE NOT NULL,
    reason VARCHAR(50) NOT NULL CHECK (reason IN ('defective', 'wrong_item', 'not_as_described', 'changed_mind'))
);

-- ============================================================================
-- INDEX DEFINITIONS - Optimize common queries and foreign key lookups
-- ============================================================================

CREATE INDEX idx_customers_segment ON customers(segment);
CREATE INDEX idx_customers_state ON customers(state);
CREATE INDEX idx_customers_signup_date ON customers(signup_date);

CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_products_sub_category ON products(sub_category);
CREATE INDEX idx_products_brand ON products(brand);

CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_order_date ON orders(order_date);
CREATE INDEX idx_orders_ship_date ON orders(ship_date);
CREATE INDEX idx_orders_ship_mode ON orders(ship_mode);
CREATE INDEX idx_orders_status ON orders(status);

CREATE INDEX idx_order_items_order_id ON order_items(order_id);
CREATE INDEX idx_order_items_product_id ON order_items(product_id);

CREATE INDEX idx_returns_order_item_id ON returns(order_item_id);
CREATE INDEX idx_returns_reason ON returns(reason);
CREATE INDEX idx_returns_return_date ON returns(return_date);

-- ============================================================================
-- SEED DATA GENERATION
-- ============================================================================

-- Insert 2,000 customers across 50 US cities with realistic distribution
INSERT INTO customers (name, email, city, state, signup_date, segment)
SELECT
    'Customer_' || n,
    'customer_' || n || '@example.com',
    (ARRAY['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'Philadelphia', 'San Antonio', 'San Diego', 'Dallas', 'San Jose',
           'Austin', 'Jacksonville', 'Fort Worth', 'Columbus', 'Indianapolis', 'Memphis', 'Boston', 'Seattle', 'Denver', 'Washington',
           'Nashville', 'Detroit', 'Oklahoma City', 'Portland', 'Las Vegas', 'Louisville', 'Baltimore', 'Milwaukee', 'Albuquerque', 'Tucson',
           'Fresno', 'Mesa', 'Sacramento', 'Atlanta', 'Long Beach', 'Kansas City', 'Virginia Beach', 'Raleigh', 'Miami', 'Minneapolis', 'Honolulu',
           'Cincinnati', 'New Orleans', 'Irving', 'Corpus Christi', 'Tallahassee', 'Buffalo', 'Jersey City', 'Anaheim', 'Stockton', 'Henderson', 'Chula Vista', 'Plano'])[((n-1) % 50) + 1],
    (ARRAY['NY', 'CA', 'IL', 'TX', 'AZ', 'PA', 'TX', 'CA', 'TX', 'CA',
           'TX', 'FL', 'TX', 'OH', 'IN', 'TN', 'MA', 'WA', 'CO', 'DC',
           'TN', 'MI', 'OK', 'OR', 'NV', 'KY', 'MD', 'WI', 'NM', 'AZ',
           'CA', 'AZ', 'CA', 'GA', 'CA', 'MO', 'VA', 'NC', 'FL', 'MN', 'HI',
           'OH', 'LA', 'TX', 'TX', 'FL', 'NY', 'NJ', 'CA', 'CA', 'NV', 'CA', 'TX'])[((n-1) % 50) + 1],
    (CURRENT_DATE - (RANDOM() * 1000)::INT * INTERVAL '1 day')::DATE,
    (ARRAY['consumer', 'corporate', 'home_office'])[((n-1) % 3) + 1]
FROM generate_series(1, 2000) AS n;

-- Insert 500 products across three categories with realistic pricing
-- Technology: laptops, monitors, keyboards, mice, headphones, etc.
INSERT INTO products (name, category, sub_category, price, cost, brand)
SELECT
    CASE
        WHEN prod_type = 1 THEN 'Laptop ' || (n % 50 + 1)
        WHEN prod_type = 2 THEN 'Monitor ' || (n % 40 + 1)
        WHEN prod_type = 3 THEN 'Keyboard ' || (n % 30 + 1)
        WHEN prod_type = 4 THEN 'Mouse ' || (n % 25 + 1)
        WHEN prod_type = 5 THEN 'Headphones ' || (n % 20 + 1)
        WHEN prod_type = 6 THEN 'Desk Chair ' || (n % 35 + 1)
        WHEN prod_type = 7 THEN 'Desk ' || (n % 30 + 1)
        WHEN prod_type = 8 THEN 'Filing Cabinet ' || (n % 20 + 1)
        WHEN prod_type = 9 THEN 'Pen Set ' || (n % 30 + 1)
        ELSE 'Notebook ' || (n % 25 + 1)
    END,
    CASE
        WHEN prod_type <= 5 THEN 'Technology'
        WHEN prod_type <= 8 THEN 'Furniture'
        ELSE 'Office Supplies'
    END,
    CASE
        WHEN prod_type = 1 THEN 'Computers'
        WHEN prod_type = 2 THEN 'Peripherals'
        WHEN prod_type = 3 THEN 'Peripherals'
        WHEN prod_type = 4 THEN 'Peripherals'
        WHEN prod_type = 5 THEN 'Audio'
        WHEN prod_type = 6 THEN 'Seating'
        WHEN prod_type = 7 THEN 'Desks'
        WHEN prod_type = 8 THEN 'Storage'
        WHEN prod_type = 9 THEN 'Writing'
        ELSE 'Paper'
    END,
    CASE
        WHEN prod_type = 1 THEN 800 + RANDOM() * 800
        WHEN prod_type = 2 THEN 200 + RANDOM() * 400
        WHEN prod_type = 3 THEN 50 + RANDOM() * 150
        WHEN prod_type = 4 THEN 20 + RANDOM() * 80
        WHEN prod_type = 5 THEN 60 + RANDOM() * 240
        WHEN prod_type = 6 THEN 150 + RANDOM() * 350
        WHEN prod_type = 7 THEN 200 + RANDOM() * 600
        WHEN prod_type = 8 THEN 100 + RANDOM() * 300
        WHEN prod_type = 9 THEN 10 + RANDOM() * 30
        ELSE 5 + RANDOM() * 15
    END,
    CASE
        WHEN prod_type = 1 THEN 400 + RANDOM() * 400
        WHEN prod_type = 2 THEN 100 + RANDOM() * 200
        WHEN prod_type = 3 THEN 20 + RANDOM() * 75
        WHEN prod_type = 4 THEN 8 + RANDOM() * 40
        WHEN prod_type = 5 THEN 25 + RANDOM() * 120
        WHEN prod_type = 6 THEN 75 + RANDOM() * 175
        WHEN prod_type = 7 THEN 100 + RANDOM() * 300
        WHEN prod_type = 8 THEN 50 + RANDOM() * 150
        WHEN prod_type = 9 THEN 4 + RANDOM() * 15
        ELSE 2 + RANDOM() * 8
    END,
    (ARRAY['Apple', 'Dell', 'HP', 'Lenovo', 'ASUS', 'Acer', 'Herman Miller', 'Steelcase', 'Knoll', 'Staples', 'Avery', 'Pen Corporation'])[((n-1) % 12) + 1]
FROM (
    SELECT n, ((n-1) / 50 + 1) as prod_type
    FROM generate_series(1, 500) AS n
);

-- Insert 15,000 orders spanning 2022-2025 with seasonal patterns
-- Q4 spike (Oct-Dec) is 40% higher volume than Q1-Q3
-- Corporate customers order primarily on weekdays (Mon-Fri)
INSERT INTO orders (customer_id, order_date, ship_date, ship_mode, status)
SELECT
    (RANDOM() * 1999 + 1)::INT,
    order_dt,
    (order_dt + (RANDOM() * 14 + 1)::INT * INTERVAL '1 day')::DATE,
    (ARRAY['Standard Class', 'Second Class', 'First Class', 'Same Day'])[((RANDOM() * 100)::INT % 4) + 1],
    'Delivered'
FROM (
    SELECT DISTINCT
        (CURRENT_DATE - INTERVAL '3 years' + ((yy * 365 + mm * 30 + dd) % 1461) * INTERVAL '1 day')::DATE AS order_dt
    FROM generate_series(0, 3) AS yy
    CROSS JOIN generate_series(0, 11) AS mm
    CROSS JOIN generate_series(1, 20 + CASE WHEN mm IN (9, 10, 11) THEN 10 ELSE 0 END) AS dd
    WHERE random() < 0.68  -- 15,000 orders / ~21,977 possible dates
    LIMIT 15000
) daily_orders;

-- Insert 45,000 order items with realistic quantities and discounts
INSERT INTO order_items (order_id, product_id, quantity, unit_price, discount)
SELECT
    o.id,
    (RANDOM() * 499 + 1)::INT,
    (RANDOM() * 4 + 1)::INT,
    (p.price * (0.85 + RANDOM() * 0.25))::DECIMAL(10, 2),
    CASE
        WHEN random() < 0.70 THEN 0.00  -- 70% no discount
        WHEN random() < 0.85 THEN (RANDOM() * 10)::DECIMAL(5, 2)  -- 15% light discount (0-10%)
        WHEN random() < 0.95 THEN (10 + RANDOM() * 10)::DECIMAL(5, 2)  -- 10% medium discount (10-20%)
        ELSE (20 + RANDOM() * 10)::DECIMAL(5, 2)  -- 5% heavy discount (20-30%)
    END
FROM (
    SELECT id, ROW_NUMBER() OVER (ORDER BY RANDOM()) as rn
    FROM orders
    LIMIT 15000
) o
CROSS JOIN LATERAL generate_series(1, (2 + RANDOM() * 4)::INT) AS item_count
CROSS JOIN LATERAL (
    SELECT * FROM products ORDER BY RANDOM() LIMIT 1
) p
LIMIT 45000;

-- Insert 800 returns with realistic reasons
-- Most returns happen 7-60 days after order
INSERT INTO returns (order_item_id, return_date, reason)
SELECT
    oi.id,
    (o.order_date + (7 + RANDOM() * 53)::INT * INTERVAL '1 day')::DATE,
    (ARRAY['defective', 'wrong_item', 'not_as_described', 'changed_mind'])[((RANDOM() * 100)::INT % 4) + 1]
FROM order_items oi
JOIN orders o ON oi.order_id = o.id
WHERE RANDOM() < 0.018  -- ~800 returns from 45,000 items (~1.8%)
LIMIT 800;

-- ============================================================================
-- DATA VALIDATION
-- ============================================================================

-- Display summary statistics
SELECT 'E-Commerce Database Seeded Successfully' AS status;
SELECT COUNT(*) AS total_customers FROM customers;
SELECT COUNT(*) AS total_products FROM products;
SELECT COUNT(*) AS total_orders FROM orders;
SELECT COUNT(*) AS total_order_items FROM order_items;
SELECT COUNT(*) AS total_returns FROM returns;
SELECT ROUND(SUM((quantity * unit_price * (100 - discount) / 100))::NUMERIC, 2) AS total_revenue FROM order_items;
