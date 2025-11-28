
# function layout:
# deleted = delete_records_by_filter(DB_PATH, "Experiment", {"is_valid": "N"}, dry_run=True)


# Example of usage:
# table: "Experiment". filters: {"is_valid": "N"}. This will delete all records from the Experiment table where is_valid is 'N'.
# table: "RawFile". filters: {"organism": "yeast", "protein: "Rfa1", "condition": "untreated", "is_valid": "N"}. This will delete all records from the RawFile table where organism is 'yeast', protein is 'Rfa1', condition is 'untreated', and is_valid is 'N'.
# table: "usser". filters: {"email": ""}. This will delete all records from the User table where email is an empty string.
# table: "Experiment". filters: {"date": "20230803"}. This will delete all records from the Experiment table where date is '2023-08-03'.