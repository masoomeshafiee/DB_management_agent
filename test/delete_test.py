
# function layout:
# deleted = delete_records_by_filter(DB_PATH, "Experiment", {"is_valid": "N"}, dry_run=True)


# Example of usage:


# -------------------------------------------------------------------------
# 1. Delete records from a table that has no foreign key dependencies.
# table: "User". filters: {"email": ""}. This will delete all records from the User table where email is an empty string.
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# 2. Delete records with filters that match multiple records.
# table: "Experiment". filters: {"is_valid": "N"}. This will delete all records from the Experiment table where is_valid is 'N'.
# table: "Experiment". filters: {"date": "20230803"}. This will delete all records from the Experiment table where date is '2023-08-03'.
#------------------------------------------------------------------------

# -------------------------------------------------------------------------
# 3. Delete records from a table that has foreign key dependencies.
# table: "TrackingFiles". filters:{"date": "20230803", "is_valid": "N"}. This will delete all records from the TrackingFiles table where date is '2023-08-03' and is_valid is 'N' in the Experiment table.
# table: "RawFile". filters: {"organism": "yeast", "protein": "Rfa1", "condition": "untreated", "is_valid": "N"}. This will delete all records from the RawFile table where organism is 'yeast', protein is 'Rfa1', condition is 'untreated', and is_valid is 'N'.
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# 4.Delete records with filters that match no records.
# table: "CaptureSettings". filters: {"capture_type": "time_lapse"}. This will delete all records from the CaptureSettings table where capture_type is 'time_lapse'.
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# 5.Delete records involving multiple foreign key dependencies.
# table: "Masks". filters: {"protein": "Rfa1", "condition": "untreated", "is_valid": "N"}. This will delete all records from the Masks table where protein is 'Rfa1', condition is 'untreated', and is_valid is 'N' in the Experiment table.
# --------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 6. delete records with invalid table name.
# table: "ImageStacks". filters: {"organism": "yeast", "protein": "Rfa1"}. This will delete all records from the ImageStacks table where organism is 'yeast' and protein is 'Rfa1'. ( there is no ImageStacks table in the database schema)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 7. delete records with empty filters.
# table: "User". filters: {}. This will delete all records from the User table.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 8. delete records with filters that match no records.
# table: "CaptureSettings". filters: {"exposure_time": "1000"}. This will delete all records from the CaptureSettings table where exposure_time is '1000'.
# ---------------------------------------------------------------------------

