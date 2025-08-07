# backend/export_config.py
# Unified Configuration Model for Data Export Jobs

import json
from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field, field_validator, ValidationInfo
from pathlib import Path

# Re-using SensorGroup from pipeline_config.py as it perfectly fits the requirement for location awareness.
# We use a try-except block for robustness in different execution environments.
try:
    from .pipeline_config import SensorGroup
except ImportError:
    # Define a fallback SensorGroup if the import fails (e.g., during initial setup)
    class SensorGroup(BaseModel):
        name: str = Field(..., description="A unique name for the sensor group/location, e.g., 'Location1'.")
        reference_sensor: str = Field(..., description="The collection name used as the time reference for THIS group.")
        collections: List[str] = Field(..., description="A list of all collection names belonging to this group.")

        @field_validator('collections')
        def reference_must_be_in_collections(cls, v, info: ValidationInfo):
            ref_sensor = info.data.get('reference_sensor')
            if ref_sensor and ref_sensor not in v:
                raise ValueError(f"The reference_sensor '{ref_sensor}' must be included in the group's collections list.")
            return v

# --- Helper Models ---

class SourceConfig(BaseModel):
    # Defines the source table in the annotation database (SQLite/Postgres)
    database_table: Literal["refined_annotations", "events", "annotations"] = Field(..., description="The table to pull source events from.")
    filters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Simple key-value filters for the source query (e.g., {'status': 'refined', 'convoy_id': None}).")

class WindowingConfig(BaseModel):
    window_size_seconds: float = Field(..., gt=0, description="The duration of each exported audio clip.")
    overlap_seconds: float = Field(..., ge=0, description="The overlap between consecutive clips.")

    @field_validator('overlap_seconds')
    def overlap_must_be_less_than_window(cls, v, info: ValidationInfo):
        # Ensures step size (window_size - overlap) is positive
        if 'window_size_seconds' in info.data and v >= info.data['window_size_seconds']:
            raise ValueError("overlap_seconds must be strictly less than window_size_seconds.")
        return v

class ProcessingConfig(BaseModel):
    # If None, the system will attempt to discover the original rate from SensorMetadata.
    target_sample_rate: Optional[int] = Field(None, gt=0, description="If set, resample all exported audio to this rate. If None, keep original.")
    windowing: Optional[WindowingConfig] = Field(None, description="If set, chunk the audio based on window and overlap. If None, export the full event duration.")

class OutputConfig(BaseModel):
    # Using Path allows the script to create the directory if it doesn't exist.
    base_directory: Path = Field(..., description="The root directory for the exported dataset.")
    # Example: "{group_name}/{vehicle_type}/{event_id_prefix}/{sensor_name}_{clip_start_ts}.{format}"
    file_path_template: str = Field(..., description="A flexible string template for generating output file paths and names.")
    format: Literal["flac", "wav", "mp3"] = Field(..., description="The output audio format.")

class TruthFileConfig(BaseModel):
    enabled: bool = Field(True, description="Whether to generate truth/manifest files.")
    mode: Literal["single", "per_group"] = Field(..., description="'single' for one master manifest, 'per_group' for manifests specific to each location.")
    filename: str = Field("manifest.csv", description="The name of the manifest file(s).")

# --- Main Export Configuration Model ---

class ExportConfig(BaseModel):
    export_job_name: str = Field(..., description="A unique identifier for this export job.")
    export_type: Literal["model_training", "single_vehicle", "convoy", "generic"] = Field(..., description="The type of export job.")
    source_config: SourceConfig
    groups: List[SensorGroup] = Field(..., description="Defines logical groupings of sensors by location, crucial for event propagation.")
    processing_config: ProcessingConfig
    output_config: OutputConfig
    truth_file_config: TruthFileConfig

    @classmethod
    def from_json(cls, config_path: str) -> "ExportConfig":
        """Loads and validates an export configuration from a JSON file."""
        p = Path(config_path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found at: {p}")
        with p.open('r') as f:
            data = json.load(f)
        # Pydantic V2 uses model_validate
        return cls.model_validate(data)

    def to_json(self, config_path: str, indent: int = 2):
        """Saves the export configuration to a JSON file."""
        with open(config_path, 'w') as f:
            # Pydantic V2 uses model_dump_json
            f.write(self.model_dump_json(indent=indent))
