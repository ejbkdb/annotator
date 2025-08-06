# backend/pipeline_config.py
import json
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, DirectoryPath, field_validator, ValidationInfo
from pathlib import Path

# --- Helper Models ---
class TimeRange(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None

class InputConfig(BaseModel):
    collections: List[str]
    time_range: TimeRange

class AlignmentConfig(BaseModel):
    offsets: Dict[str, int] = Field(default_factory=dict, description="All sensor offsets in milliseconds relative to their group's reference sensor.")

class ProcessingConfig(BaseModel):
    window_size_seconds: float = Field(..., gt=0)
    overlap_seconds: float = Field(..., ge=0)
    target_sample_rate: int = Field(..., gt=0)

class OutputConfig(BaseModel):
    base_directory: DirectoryPath
    structure: str
    format: str = Field(..., pattern=r"^(flac|wav|mp3)$")

class SensorGroup(BaseModel):
    name: str = Field(..., description="A unique name for the sensor group, e.g., 'Location1' or 'L1'.")
    reference_sensor: str = Field(..., description="The collection name to be used as the time reference for THIS group.")
    collections: List[str] = Field(..., description="A list of all collection names belonging to this group.")

    @field_validator('collections')
    def reference_must_be_in_collections(cls, v, info: ValidationInfo):
        ref_sensor = info.data.get('reference_sensor')
        if ref_sensor and ref_sensor not in v:
            raise ValueError(f"The reference_sensor '{ref_sensor}' must be included in the group's collections list.")
        return v

# --- Main Configuration Model ---
class PipelineConfig(BaseModel):
    pipeline_id: str
    input: InputConfig
    alignment: AlignmentConfig
    groups: List[SensorGroup] = Field(default_factory=list, description="Defines logical groupings of sensors by location, each with its own reference.")
    processing: ProcessingConfig
    output: OutputConfig

    @classmethod
    def from_json(cls, config_path: str) -> "PipelineConfig":
        """Loads and validates a pipeline configuration from a JSON file."""
        p = Path(config_path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found at: {p}")
        with p.open('r') as f:
            data = json.load(f)
        return cls(**data)

    def to_json(self, config_path: str, indent: int = 2):
        """Saves the pipeline configuration to a JSON file."""
        with open(config_path, 'w') as f:
            f.write(self.model_dump_json(indent=indent))

    # --- THIS IS THE CORRECTED VALIDATOR ---
    @field_validator('groups')
    def check_group_collections_are_in_input(cls, v, info: ValidationInfo):
        """
        Ensures that every collection listed within a group is also present
        in the main `input.collections` list.
        """
        # The `info.data` dictionary contains fields that have already been validated.
        # We must check if 'input' is present before trying to access it.
        if 'input' not in info.data:
            # This can happen if 'input' fails validation first. We can't proceed.
            return v

        # CORRECT: Access the 'input' object, which is an InputConfig instance.
        input_config: InputConfig = info.data['input']
        
        # CORRECT: Access the 'collections' attribute of the InputConfig object.
        all_known_collections = set(input_config.collections)

        for group in v:
            for collection in group.collections:
                if collection not in all_known_collections:
                    # This is a more informative error/warning.
                    # Using a print statement for a warning is fine here.
                    print(f"Warning: Collection '{collection}' in group '{group.name}' is not listed in the main input.collections list.")
        return v