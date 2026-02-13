
# function layout:
# deleted = delete_records_by_filter(DB_PATH, "Experiment", {"is_valid": "N"}, dry_run=True)


# Example of usage:


# -------------------------------------------------------------------------
# 1. Delete records from a table that has no foreign key dependencies.
# user prompts: "Delete all records (no limit on the number of records) from the User table with empty email addresses in the database in this directory: example_data/db/Reyes_lab_data.db."
# table: "User". filters: {"email": ""}. This will delete all records from the User table where email is an empty string.
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# 2. Delete records with filters that match multiple records.
# user prompt: "Delete all experiments that are marked as invalid in the database stored in this directory: example_data/db/Reyes_lab_data.db."
# table: "Experiment". filters: {"is_valid": "N"}. This will delete all records from the Experiment table where is_valid is 'N' in the database in this directory: example_data/db/Reyes_lab_data.db."
# user prompt: "Delete all experiments that took place on August 3rd, 2023, in this directory: example_data/db/Reyes_lab_data.db.""
# table: "Experiment". filters: {"date": "20230803"}. This will delete all records from the Experiment table where date is '2023-08-03', in the database in this directory: example_data/db/Reyes_lab_data.db."
#------------------------------------------------------------------------

# -------------------------------------------------------------------------
# 3. Delete records from a table that has foreign key dependencies.
# user prompt: " Delete all invalid tracking files from August 3rd, 2023, in the database in this directory: example_data/db/Reyes_lab_data.db."
# table: "TrackingFiles". filters:{"date": "20230803", "is_valid": "N"}. This will delete all records from the TrackingFiles table where date is '2023-08-03' and is_valid is 'N' in the Experiment table in the database in this directory: example_data/db/Reyes_lab_data.db."
# user prompt: "Delete all yeast Rfa1 raw files that are untreated marked as invalid, in the database in this directory: example_data/db/Reyes_lab_data.db."
# table: "RawFile". filters: {"organism": "yeast", "protein": "Rfa1", "condition": "untreated", "is_valid": "N"}. This will delete all records from the RawFile table where organism is 'yeast', protein is 'Rfa1', condition is 'untreated', and is_valid is 'N'.
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# 4.Delete records with filters that match no records.
# user prompt: "Delete all time-lapse capture settings, in the database in this directory: example_data/db/Reyes_lab_data.db."
# table: "CaptureSettings". filters: {"capture_type": "time_lapse"}. This will delete all records from the CaptureSettings table where capture_type is 'time_lapse'.
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# 5.Delete records involving multiple foreign key dependencies.
# user prompt: "Delete all masks for invalid experiments for yeast Rfa1 protein that are untreated, in the database in this directory: example_data/db/Reyes_lab_data.db."
# table: "Masks". filters: {"protein": "Rfa1", "condition": "untreated", "is_valid": "N"}. This will delete all records from the Masks table where protein is 'Rfa1', condition is 'untreated', and is_valid is 'N' in the Experiment table.
# --------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 6. delete records with invalid table name.
# user prompt: "Delete all records from the ImageStacks table where organism is yeast and protein is Rfa1, in the database in this directory: example_data/db/Reyes_lab_data.db."
# table: "ImageStacks". filters: {"organism": "yeast", "protein": "Rfa1"}. This will delete all records from the ImageStacks table where organism is 'yeast' and protein is 'Rfa1'. ( there is no ImageStacks table in the database schema). 
# so the agent should respond with an error message indicating that the table does not exist and no records should be deleted.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 7. delete records with empty filters.
# user prompt: "Delete all records from the User table, in the database in this directory: example_data/db/Reyes_lab_data.db."
# table: "User". filters: {}. This will delete all records from the User table.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 8. delete records with filters that match no records.
# user prompt: "Delete all capture settings with exposure time of 1000, in the database in this directory: example_data/db/Reyes_lab_data.db."
# table: "CaptureSettings". filters: {"exposure_time": "1000"}. This will delete all records from the CaptureSettings table where exposure_time is '1000'. 
# If there are no records with exposure_time of '1000', The agent should respond with a message indicating that no records matched the filters and no records should be deleted.
# ---------------------------------------------------------------------------

