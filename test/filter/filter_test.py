# test cases for the filter inference agent:
#
# Prompt tests for filter_infer_agent:

# ------------------------------------------------------------------------
# 1. Valid criteria with single filter
# User prompt: "Find all records for organism yeast, in the database in this directory: example_data/db/Reyes_lab_data.db."
# Expected output: {"organism": "yeast"}
# ------------------------------------------------------------------------

# ------------------------------------------------------------------------
# 2. Valid criteria with multiple filters
# User prompt: "Delete all records for organism E.coli and protein DnaA, in the database in this directory: example_data/db/Reyes_lab_data.db."
# Expected output: {"organism": "E.coli", "protein": "DnaA"}
# ------------------------------------------------------------------------

# ------------------------------------------------------------------------
# 3. Criteria with unsupported fields
# User prompt: "Find all records for organism yeast and location lab1, in the database in this directory: example_data/db/Reyes_lab_data.db."
# Expected output: {error: "The provided criteria includes unsupported fields:{unsupported fields}. Please use only the supported fields: {list of supported fields}."}
# ------------------------------------------------------------------------

# ------------------------------------------------------------------------
# 4. Ambiguous criteria
# User prompt: "Delete all records for protein Rfa1 after treatment with cpt, in the database in this directory: example_data/db/Reyes_lab_data.db."
# Expected output: {error: "The provided criteria is ambiguous. Please provide more specific details." }
# ------------------------------------------------------------------------

# ------------------------------------------------------------------------
# 5. Incomplete criteria
# User prompt: "Find all records for organism, in the database in this directory: example_data/db/Reyes_lab_data.db."
# Expected output: {error: "The provided criteria is incomplete. Please provide values for the specified fields:{incomplete fields}}.""
# ------------------------------------------------------------------------

# ------------------------------------------------------------------------
# 6. Criteria not related to filter inference
# User prompt: "Where does this database belong to?"
# Expected output: {error:"I am only allowed to infer filters for database operations."}
# ------------------------------------------------------------------------

# -------------------------------------------------------------------------
# 7. Valid criteria with date filter
# User prompt: "Find all experiment records for date 2023-08-03, in the database in this directory: example_data/db/Reyes_lab_data.db."
# Expected output: {"date": "20230803"}
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# 8. Valid criteria with exposure_time filter
# User prompt: "Delete all capture settings records with exposure time 2.5 seconds, in the database in this directory: example_data/db/Reyes_lab_data.db."
# Expected output: {"exposure_time": 2.5}
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# 9. Valid criteria with concentration_unit filter
# User prompt: "Find all records with concentration unit in nM, in the database in this directory: example_data/db/Reyes_lab_data.db."
# Expected output: {"concentration_unit": "nM"}
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# 10. Criteria with wrong time_interval unit filter
# User prompt: "Delete all records with time interval of 5 minutes, in the database in this directory: example_data/db/Reyes_lab_data.db."
# Expected output: {error: "The provided criteria is incomplete. Please provide values for the specified fields: time_interval should be in seconds."}
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# 11. Valid criteria with is_valid filter
# User prompt: "Find all experiment records that are not valid, in the database in this directory: example_data/db/Reyes_lab_data.db."
# Expected output: {"is_valid": "N"}
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# 12. valid criteria with email filter
# User prompt: "Delete all user records with email, in the database in this directory: example_data/db/Reyes_lab_data.db."
# Expected output: {"email": ""}
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# 13. Ambiguous criteria with multiple unsupported fields
# User prompt: "Delete records for organism yeast and location lab1 and date, in the database in this directory: example_data/db/Reyes_lab_data.db."
# Expected output: {error: "The provided criteria is ambiguous. Please provide more specific details {ambiguous details} and includes unsupported fields: {unsupported fields}. Please use only the supported fields: {list of supported fields}."}
# Note: The user should specify what table they want to delete records from.
# -------------------------------------------------------------------------