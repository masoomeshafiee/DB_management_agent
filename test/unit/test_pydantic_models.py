"""Unit tests for filter and deletion Pydantic models."""

import pytest
from pydantic import ValidationError

from agent.pydantic_models import ALLOWED_TABLES, TABLE_ALIASES, DeletionSchema, StrictLabFilters

pytestmark = pytest.mark.unit


# ---------- StrictLabFilters ----------

@pytest.mark.parametrize("raw, expected", [
    (True, "Y"), (False, "N"),
    ("yes", "Y"), ("Y", "Y"), ("true", "Y"), ("valid", "Y"),
    ("NO", "N"), ("false", "N"), (" invalid ", "N"),
])
def test_is_valid_is_normalized_to_the_values_the_database_stores(raw, expected):
    assert StrictLabFilters(is_valid=raw).is_valid == expected


def test_unrecognized_is_valid_value_is_rejected():
    with pytest.raises(ValidationError):
        StrictLabFilters(is_valid="maybe")


@pytest.mark.parametrize("raw", ["2023-08-03", "2023/08/03", "2023 08 03", "20230803"])
def test_date_separators_are_stripped(raw):
    assert StrictLabFilters(date=raw).date == "20230803"


def test_date_that_is_not_eight_digits_is_rejected():
    with pytest.raises(ValidationError):
        StrictLabFilters(date="Aug 3")


def test_unknown_filter_key_is_rejected():
    with pytest.raises(ValidationError):
        StrictLabFilters(colour="blue")


def test_negative_exposure_time_is_rejected():
    with pytest.raises(ValidationError):
        StrictLabFilters(exposure_time=-1.0)


def test_unsupported_concentration_unit_is_rejected():
    with pytest.raises(ValidationError):
        StrictLabFilters(concentration_unit="g/L")


def test_dump_contains_only_the_filters_that_were_set():
    filters = StrictLabFilters(organism="yeast", is_valid=False)
    assert filters.model_dump(exclude_none=True) == {"organism": "yeast", "is_valid": "N"}


# ---------- DeletionSchema ----------

@pytest.mark.parametrize("raw, expected", [
    ("track", "TrackingFiles"),
    ("tracking files", "TrackingFiles"),
    ("raw files", "RawFiles"),
    ("analysis result", "AnalysisResults"),
    ("person", "User"),
    ("TrackingFiles", "TrackingFiles"),
])
def test_table_aliases_map_to_canonical_names(raw, expected):
    assert DeletionSchema(table=raw).table == expected


def test_unknown_table_is_rejected():
    with pytest.raises(ValidationError):
        DeletionSchema(table="Spaceships")


def test_limit_defaults_to_none_so_delete_all_is_not_silently_capped():
    assert DeletionSchema(table="TrackingFiles").limit is None


@pytest.mark.parametrize("limit", [0, 1001])
def test_limit_outside_allowed_range_is_rejected(limit):
    with pytest.raises(ValidationError):
        DeletionSchema(table="TrackingFiles", limit=limit)


def test_db_path_defaults_to_none_so_the_model_never_has_to_invent_one():
    assert DeletionSchema(table="TrackingFiles").db_path is None


def test_every_alias_points_to_an_allowed_table():
    assert set(TABLE_ALIASES.values()) <= ALLOWED_TABLES
