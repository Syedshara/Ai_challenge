-- Post-import setup for PAS Live Monitor demo
-- Runs after employees DB is imported

USE employees;

-- ── 1. Add metadata JSON column to employees ──────────────────────────────
-- Enables JSON_EXTRACT anti-pattern demo
-- This init script only runs once on fresh container creation, so no IF NOT EXISTS needed.

ALTER TABLE employees ADD COLUMN metadata JSON;

-- Populate metadata for employees with a current department assignment
UPDATE employees e
JOIN dept_emp de ON e.emp_no = de.emp_no AND de.to_date = '9999-01-01'
JOIN departments d ON de.dept_no = d.dept_no
SET e.metadata = JSON_OBJECT(
    'hire_year',     YEAR(e.hire_date),
    'gender_code',   e.gender,
    'department',    d.dept_name,
    'tenure_years',  TIMESTAMPDIFF(YEAR, e.hire_date, CURDATE())
);

-- For employees without a current department, set minimal metadata
UPDATE employees
SET metadata = JSON_OBJECT(
    'hire_year',   YEAR(hire_date),
    'gender_code', gender
)
WHERE metadata IS NULL;


-- ── 2. Grant monitor user full SELECT privileges ──────────────────────────

GRANT SELECT ON employees.* TO 'monitor'@'%';
GRANT PROCESS ON *.* TO 'monitor'@'%';
FLUSH PRIVILEGES;

-- ── 3. Verification ───────────────────────────────────────────────────────
SELECT
    table_name,
    table_rows
FROM information_schema.tables
WHERE table_schema = 'employees'
ORDER BY table_rows DESC;
