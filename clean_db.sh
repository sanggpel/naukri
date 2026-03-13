#!/bin/bash
# Clean the database — keep only applied, rejected, and not_relevant applications.
# Also clears seen_jobs so scout finds fresh results.

DB="data/tracker.db"

if [ ! -f "$DB" ]; then
    echo "Database not found at $DB"
    exit 1
fi

echo "Before:"
sqlite3 "$DB" "SELECT status, COUNT(*) FROM applications GROUP BY status;"
echo ""

sqlite3 "$DB" "DELETE FROM applications WHERE status NOT IN ('applied', 'rejected', 'not_relevant');"
sqlite3 "$DB" "DELETE FROM seen_jobs;"

echo "After:"
sqlite3 "$DB" "SELECT status, COUNT(*) FROM applications GROUP BY status;"
echo ""
echo "Done. Seen jobs cleared — scout will find fresh results."
