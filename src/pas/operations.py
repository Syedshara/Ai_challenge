"""Insurance PAS operations — each maps to a real SQL query with an insurance narrative.

The MySQL Employees Sample Database is reframed as insurance data:
  employees (300K)  -> insurance policy records
  salaries  (2.8M)  -> premium payment history
  dept_emp  (331K)  -> policy-department assignments
  departments (9)   -> business line config
  titles    (443K)  -> coverage type records
  metadata JSON     -> policy JSON attributes (added in docker/initdb/02_post_setup.sql)
"""

PAS_OPERATIONS = [
    {
        "id": 1,
        "name": "Monthly Premium Report",
        "narrative": "Finance team requesting full premium payment history for monthly reconciliation...",
        "sql": "SELECT * FROM salaries",
        "problematic": True,
        "expected_issue": "Full table scan on 2.8M premium records — no WHERE clause, no LIMIT",
    },
    {
        "id": 2,
        "name": "Policy Holder Directory Lookup",
        "narrative": "Customer service searching policyholder records by first name...",
        "sql": "SELECT * FROM employees WHERE first_name = 'Georgi'",
        "problematic": True,
        "expected_issue": "Unindexed column filter — full scan of 300K policy records",
    },
    {
        "id": 3,
        "name": "Compliance Policy Audit",
        "narrative": "Compliance team auditing policies by enrollment year for regulatory report...",
        "sql": (
            "SELECT emp_no, first_name, last_name, metadata "
            "FROM employees "
            "WHERE JSON_EXTRACT(metadata, '$.hire_year') = 1986"
        ),
        "problematic": True,
        "expected_issue": "JSON_EXTRACT in WHERE — function prevents index use, full scan required",
    },
    {
        "id": 4,
        "name": "Active High-Value Policies Report",
        "narrative": "Management requesting high-premium active policy details across all business lines...",
        "sql": (
            "SELECT e.emp_no, e.first_name, e.last_name, "
            "s.salary, t.title, d.dept_name "
            "FROM employees e "
            "JOIN salaries s ON e.emp_no = s.emp_no "
            "JOIN titles t ON e.emp_no = t.emp_no "
            "JOIN dept_emp de ON e.emp_no = de.emp_no "
            "JOIN departments d ON de.dept_no = d.dept_no "
            "WHERE s.salary > 80000"
        ),
        "problematic": True,
        "expected_issue": "4-table JOIN without date range filters — no to_date bounds on current records",
    },
    {
        "id": 5,
        "name": "Claims Subquery Analysis",
        "narrative": "Actuarial team pulling premium history for long-tenure policyholders pre-1990...",
        "sql": (
            "SELECT * FROM salaries "
            "WHERE emp_no IN ("
            "    SELECT emp_no FROM employees WHERE hire_date < '1990-01-01'"
            ")"
        ),
        "problematic": True,
        "expected_issue": "Correlated subquery with IN — drives repeated full scans",
    },
    {
        "id": 6,
        "name": "Single Policy Fast Lookup",
        "narrative": "Claims adjustor doing point lookup for policy #10001...",
        "sql": (
            "SELECT emp_no, first_name, last_name, hire_date "
            "FROM employees WHERE emp_no = 10001"
        ),
        "problematic": False,
        "expected_issue": None,
    },
]
