#!/bin/bash
# Download and import the MySQL Employees Sample Database
# Source: https://github.com/datacharmer/test_db (CC-BY-SA)
set -e

echo "==> Checking for curl..."
if ! command -v curl &>/dev/null; then
    echo "ERROR: curl not found in container. Installing..."
    apt-get update -qq && apt-get install -y -qq curl
fi

echo "==> Downloading MySQL Employees Sample Database (~30MB)..."
cd /tmp

# Try primary URL, fall back to alternative
URL="https://github.com/datacharmer/test_db/archive/refs/heads/master.tar.gz"

MAX_RETRIES=3
for i in $(seq 1 $MAX_RETRIES); do
    echo "    Attempt $i/$MAX_RETRIES..."
    if curl -fsSL --connect-timeout 30 --max-time 120 -o employees_db.tar.gz "$URL"; then
        echo "    Download OK"
        break
    fi
    if [ "$i" -eq "$MAX_RETRIES" ]; then
        echo "ERROR: Failed to download employees database after $MAX_RETRIES attempts."
        echo "       Check network access from the Docker container."
        exit 1
    fi
    echo "    Retrying in 5s..."
    sleep 5
done

echo "==> Extracting archive..."
tar -xzf employees_db.tar.gz
cd test_db-master

echo "==> Importing employees database (4.1M rows — this takes 2-3 minutes)..."
mysql -u root -p"${MYSQL_ROOT_PASSWORD}" < employees.sql

echo "==> Done. Tables imported:"
echo "    employees(300K), salaries(2.8M), titles(443K), dept_emp(331K), departments(9)"
