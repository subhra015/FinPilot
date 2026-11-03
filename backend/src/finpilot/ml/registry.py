"""Trusted model registry and safe artifact persistence with cryptographic verification (Layer 9).

Governed by:
- SECURITY.md §2 (Trust Boundaries & Threat Mitigation)
- SECURITY_CHECKLIST.md SEC-06, SEC-18, SEC-23
- Layer 9 Gate: Safe model loading; never load untrusted pickle/joblib from user uploads;
  only load trusted, versioned artifacts with integrity checks and controlled paths.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Final

import joblib  # type: ignore[import-untyped]

from finpilot.schemas.errors import DomainValidationError, ErrorCode

from .models import ModelArtifactMetadata
from .pipeline import MLSelectionPipeline

DEFAULT_MODELS_DIR: Final[Path] = Path("artifacts/models")
MODEL_ID_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]{3,100}$")


class UntrustedArtifactError(DomainValidationError):
    """Raised when an artifact fails cryptographic verification or violates trust boundaries."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            field="artifact",
            code=ErrorCode.PERMISSION_DENIED,
        )


class ModelRegistry:
    """Manages trusted, versioned ML model artifacts with cryptographic integrity checks.

    Guarantees:
    1. Path Containment: Restricts model loading to a controlled server-authoritative directory.
       Rejects directory traversal (e.g. `../`) and absolute paths outside the registry.
    2. Zero User-Uploaded Models: Refuses to load models from untrusted client uploads.
    3. Cryptographic Tamper Detection: Computes SHA-256 of the model file prior to unpickling;
       rejects corrupted or mutated binaries immediately.
    4. Immutable Metadata: Every model artifact is linked to its feature schema, commit hash,
       and dependency versions.
    """

    def __init__(self, registry_dir: Path | str | None = None) -> None:
        self.registry_dir = Path(registry_dir or DEFAULT_MODELS_DIR).resolve()
        self.registry_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_and_resolve_model_id(self, model_id: str) -> Path:
        """Validate model_id syntax and ensure the target directory is contained within registry."""
        if not MODEL_ID_REGEX.match(model_id):
            raise UntrustedArtifactError(
                f"Invalid or uncontained model_id: {model_id!r}. "
                f"Must match regex {MODEL_ID_REGEX.pattern}."
            )

        model_dir = (self.registry_dir / model_id).resolve()
        # Path traversal guard
        if not str(model_dir).startswith(str(self.registry_dir)):
            raise UntrustedArtifactError(
                f"Path traversal detected: {model_id!r} resolves outside trusted directory."
            )

        return model_dir

    def save_model(
        self,
        pipeline: MLSelectionPipeline,
        metadata: ModelArtifactMetadata,
    ) -> tuple[Path, Path]:
        """Save pipeline binary and metadata JSON to registry with SHA-256 digest."""
        model_dir = self._sanitize_and_resolve_model_id(metadata.model_id)
        model_dir.mkdir(parents=True, exist_ok=True)

        artifact_file = model_dir / f"{metadata.model_id}.joblib"
        meta_file = model_dir / "metadata.json"

        # 1. Dump pipeline binary
        joblib.dump(pipeline, artifact_file, compress=3)

        # 2. Compute SHA-256 digest of serialized binary
        sha256 = hashlib.sha256()
        with open(artifact_file, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        artifact_checksum = sha256.hexdigest()

        # 3. Update metadata with actual binary checksum
        saved_metadata = metadata.model_copy(update={"artifact_checksum": artifact_checksum})
        pipeline.metadata = saved_metadata

        # 4. Save metadata JSON
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(saved_metadata.model_dump(mode="json"), f, indent=2, sort_keys=True)

        return artifact_file, meta_file

    def load_model(
        self,
        model_id: str,
    ) -> tuple[MLSelectionPipeline, ModelArtifactMetadata]:
        """Safely load and verify an authorized model artifact. Fails closed on any tampering."""
        model_dir = self._sanitize_and_resolve_model_id(model_id)

        meta_file = model_dir / "metadata.json"
        artifact_file = model_dir / f"{model_id}.joblib"

        if not meta_file.exists() or not artifact_file.exists():
            raise UntrustedArtifactError(
                f"Model artifact {model_id!r} does not exist in trusted registry."
            )

        # 1. Load and parse metadata
        try:
            with open(meta_file, encoding="utf-8") as f:
                meta_json = json.load(f)
            metadata = ModelArtifactMetadata.model_validate(meta_json)
        except Exception as e:
            raise UntrustedArtifactError(f"Failed to parse metadata: {e}") from e

        # 2. Verify Cryptographic Integrity: compute SHA-256 BEFORE loading joblib binary
        sha256 = hashlib.sha256()
        with open(artifact_file, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        computed_checksum = sha256.hexdigest()

        if computed_checksum != metadata.artifact_checksum:
            raise UntrustedArtifactError(
                f"Integrity check failed for model {model_id!r}: computed checksum "
                f"{computed_checksum} != registered {metadata.artifact_checksum}."
            )

        # 3. Deserialize trusted binary
        loaded_pipeline = joblib.load(artifact_file)
        if not isinstance(loaded_pipeline, MLSelectionPipeline):
            raise UntrustedArtifactError(
                f"Loaded object for {model_id!r} is not an MLSelectionPipeline instance."
            )

        loaded_pipeline.metadata = metadata
        return loaded_pipeline, metadata
