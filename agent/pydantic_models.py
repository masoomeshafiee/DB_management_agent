import re
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, Any, Literal


TABLE_ALIASES = {
    "tracking": "TrackingFiles",
    "track": "TrackingFiles",
    "raw": "RawFiles",
    "analysis file": "AnalysisFiles",
    "analysis result": "AnalysisResults",
    "capture": "CaptureSetting",
    "setting": "CaptureSetting",
    "condition": "Condition",
    "experiment": "Experiment",
    "mask": "Masks",
    "organism": "Organism",#should add other alternatives for organism like "cell" or "model" if needed
    "protein": "Protein",
    "user": "User",
    "person": "User"
}

ALLOWED_TABLES = frozenset({
    "AnalysisFiles",
    "AnalysisResultExperiment",
    "AnalysisResults",
    "CaptureSetting",
    "Condition",
    "Experiment",
    "ExperimentAnalysisFiles",
    "Masks",
    "Organism",
    "Protein",
    "RawFiles",
    "TrackingFiles",
    "User",
})


class LabFilters(BaseModel):
    organism: Optional[str] = None
    protein: Optional[str] = None
    strain: Optional[str] = None
    condition: Optional[str] = None
    user_name: Optional[str] = None
    email: Optional[str] = None
    comment: Optional[str] = None
    
    capture_setting_id: Optional[int] = None
    capture_type: Optional[str] = None
    replicate: Optional[int] = None
    experiment_id: Optional[int] = None
    raw_file_id: Optional[int] = None
    raw_file_name: Optional[str] = None
    tracking_file_id: Optional[int] = None
    mask_id: Optional[int] = None
    analysis_file_id: Optional[int] = None
    analysis_result_id: Optional[int] = None
    
    raw_file_type: Optional[str] = None
    mask_type: Optional[str] = None
    mask_file_type: Optional[str] = None
    analysis_file_type: Optional[str] = None
    analysis_result_type: Optional[str] = None
    
    is_valid: Optional[bool] = None

    #strict formatting enfrcment
    date: Optional[str] = Field(default=None, pattern=r"^\d{8}$", description="Date in YYYYMMDD format as a string, e.g., '20230915'")
    exposure_time: Optional[float] = Field(default=None, ge=0, description="Exposure time in seconds (float)")
    time_interval: Optional[float] = Field(default=None, ge=0, description="Time interval in seconds (float)")
    concentration_unit: Optional[Literal["nM", "uM", "mM", "M"]] = None
    concentration_value: Optional[float] = Field(default=None, ge=0, description="Concentration value as a non-negative float")
    dye_concentration_unit: Optional[Literal["nM", "uM", "mM", "M"]] = None
    dye_concentration_value: Optional[float] = Field(default=None, ge=0, description="Dye concentration value as a non-negative float")

    @field_validator("date", mode="before")
    @classmethod
    def validate_date_format(cls, v: Any) -> str:
        if isinstance(v, str):
            return  re.sub(r'[-/\s]', '', v)
        return v


class StrictLabFilters(LabFilters):
    """Database-boundary validator that rejects unsupported filter fields."""

    model_config = ConfigDict(extra="forbid")


class DeletionSchema(BaseModel):
    """Structured request produced by the deletion filter agent."""

    db_path: str = Field(
        default="./data/sample_data.db",
        min_length=1,
        description="Path to the SQLite database file.",
    )
    table: Literal[
        "AnalysisFiles",
        "AnalysisResultExperiment",
        "AnalysisResults",
        "CaptureSetting",
        "Condition",
        "Experiment",
        "ExperimentAnalysisFiles",
        "Masks",
        "Organism",
        "Protein",
        "RawFiles",
        "TrackingFiles",
        "User",
    ] = Field(
        ...,
        description="Canonical name of the table containing records to delete.",
    )
    filters: LabFilters = Field(
        default_factory=LabFilters,
        description="Validated criteria selecting the records to delete.",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=1000,
        description="Maximum number of records included in the deletion.",
    )

    @field_validator("table", mode="before")
    @classmethod
    def map_table_names(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        normalized = value.strip().lower()
        for alias, table_name in TABLE_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", normalized):
                return table_name
        return value.strip()
