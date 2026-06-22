# Shared Fixtures

Store reusable test inputs here, including:

- Small SQLite database templates
- CSV metadata samples
- Expected exported query results
- Audit-log examples
- Mock agent event payloads

Tests should copy database templates into a temporary directory before making
changes. They should never modify the repository's primary sample database.
