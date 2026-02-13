# test cases for insertion database operation for the insert agent.

# ------------------------Validation Test Cases----------------------------
# test cases for the validation of to be inserted rows:

# function layout:
# invalid_rows = validate_csv(metadata_csv_path, metadata_output_path)
# 
# different test cases for the validation agent:
#
# ------------------------------------------------------
# 1. Test with a valid CSV file.
# user prompt: validate the CSV file located at ./test/insertion/valid.csv and return any invalid/skipped rows.
# the agent needs to call invalid_rows = validate_csv(test/insertion/valid.csv, metadata_output_path)
# expected output: the agent should return an empty list of invalid rows.
# -----------------------------------------------------
# -----------------------------------------------------
# 2. Test with an empty CSV file:
# user prompt: validate the CSV file located at ./test/insertion/empty.csv and return any invalid/skipped rows.
# the agent needs to call invalid_rows = validate_csv(test/insertion/empty.csv, metadata_output_path)
# expected output: the agent should return an empty list of invalid rows, and mention that the CSV file is empty.
# -----------------------------------------------------
# -----------------------------------------------------
# 3. Test with a CSV file that has only headers:
# user prompt: validate the CSV file located at test/insertion/only_headers.csv and return any invalid/skipped rows.
# the agent needs to call invalid_rows = validate_csv(test/insertion/only_headers.csv, metadata_output_path)
# expected output: the agent should return an empty list of invalid rows, and mention that there are no data rows to validate.
# -----------------------------------------------------
# -----------------------------------------------------
# 4. Test with a CSV file that has missing values:
# user prompt: validate the CSV file located at test/insertion/missing_values.csv and return any invalid/skipped rows.
# the agent needs to call invalid_rows = validate_csv(test/insertion/missing_values.csv, metadata_output_path)
# expected output: the agent should return the rows with missing values as invalid rows.
# -----------------------------------------------------
# 5. Test with a CSV file that has mixed valid and invalid rows:
# user prompt: validate the CSV file located at test/insertion/mixed_valid_invalid.csv and return any invalid/skipped rows.
# the agent needs to call invalid_rows = validate_csv(test/insertion/mixed_valid_invalid.csv, metadata_output_path)
# in that file there are records with 1.invalid data types, 2.missing values, 3.invalid formats, 4.special characters, 5.valid rows.
# expected output: the agent should return only the invalid rows.
# -----------------------------------------------------
# ------------------------------------------------------


# # ------------------------Insertion Test Cases----------------------------
# test cases for the insertion of validated rows into the database:

# function layout:
# skipped_rows = insert_from_csv(CSV_PATH, DB_PATH, skipped_rows)
#
# test cases for the insertion agent:
# ------------------------------------------------------
# 1. Test inserting valid rows.
# user prompt: insert the valid rows from the CSV file located at test/insertion/valid_rows_non_existing_db.csv, into the database in this directory: example_data/db/Reyes_lab_data.db." and return any skipped/invalid rows.
# The agent needs to call skipped_rows = insert_from_csv(test/insertion/valid_rows_non_existing_db.csv, DB_PATH, skipped_rows)
# expected output: the agent should insert all valid rows and return an empty skipped_rows.
# ------------------------------------------------------
# 2. Test inserting valid rows into a database with existing records (to check for duplicates).
# user prompt: insert the valid rows from the CSV file located at test/insertion/valid_rows_existing_db.csv , into the database in this directory: example_data/db/Reyes_lab_data.db." and return any skipped/invalid rows.
# The agent needs to call skipped_rows = insert_from_csv(test/insertion/valid_rows_existing_db.csv, DB_PATH, skipped_rows)
# expected output: the agent should insert only non-duplicate rows and skip duplicates and return them in skipped_rows.
# ------------------------------------------------------
# ------------------------------------------------------
# 3. Test inserting rows with foreign key dependencies.
# user prompt: insert the rows from the CSV file located at test/insertion/rows_with_foreign_keys.csv , into the database in this directory: example_data/db/Reyes_lab_data.db." and return any skipped/invalid rows.
# The agent needs to call skipped_rows = insert_from_csv(test/insertion/rows_with_foreign_keys.csv, DB_PATH, skipped_rows)
# expected output: the agent should insert rows that have valid foreign key references and skip those that do not, returning them in skipped_rows.
# ------------------------------------------------------
# ------------------------------------------------------
