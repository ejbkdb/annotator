# backend/pipeline_config.py
import json
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, DirectoryPath, FilePath

class TimeRange(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None

class InputConfig(BaseModel):
    collections: List[str]
    time_range: TimeRange

class AlignmentConfig(BaseModel):
    reference_sensor: str
    offsets: Dict[str, int] = Field(default_factory=dict)

class ProcessingConfig(BaseModel):
    window_size_seconds: float = Field(..., gt=0)
    overlap_seconds: float = Field(..., ge=0)
    target_sample_rate: int = Field(..., gt=0)

class OutputConfig(BaseModel):
    base_directory: DirectoryPath
    structure: str
    format: str = Field(..., pattern=r"^(flac|wav|mp3)$")

class PipelineConfig(BaseModel):
    pipeline_id: str
    input: InputConfig
    alignment: AlignmentConfig
    processing: ProcessingConfig
    output: OutputConfig

    @classmethod
    def from_json(cls, config_path: FilePath) -> "PipelineConfig":
        """Loads and validates a pipeline configuration from a JSON file."""
        with open(config_path, 'r') as f:
            data = json.load(f)
        return cls(**data)

    def to_json(self, config_path: str, indent: int = 2):
        """Saves the pipeline configuration to a JSON file."""
        with open(config_path, 'w') as f:
            f.write(self.model_dump_json(indent=indent))