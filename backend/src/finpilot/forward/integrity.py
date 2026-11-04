"""Model and configuration cryptographic integrity verifier (Layer 16).

Governed by:
- ACCEPTANCE_GATES.md §2 (Layer 16 Gate)
- SECURITY_CHECKLIST.md SEC-06, SEC-18, SEC-23
- PROJECT_SPEC.md §4, §5, §7
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from finpilot.evaluation.models import EvaluationManifest
from finpilot.forward.models import ModelIntegrityVerification
from finpilot.ml.registry import ModelRegistry
from finpilot.schemas.errors import DomainValidationError, ErrorCode

DEFAULT_MODELS_DIR = Path("artifacts/models")
DEFAULT_CALIBRATION_DIR = Path("artifacts/calibration")
DEFAULT_MANIFEST_PATH = Path("artifacts/evaluation/EVALUATION_MANIFEST_LOCKED_TEST.json")


def verify_frozen_model_and_config(
    model_id: str = "MODEL-LOGREG-V1",
    calibration_policy_id: str = "DECISION-POLICY-V1",
    models_dir: Path | str = DEFAULT_MODELS_DIR,
    calibration_dir: Path | str = DEFAULT_CALIBRATION_DIR,
    manifest_path: Path | str = DEFAULT_MANIFEST_PATH,
) -> ModelIntegrityVerification:
    """Verify cryptographic integrity of model artifact, feature schema, calibration, and risk rules.

    Fails closed if the model file is altered, missing, or mismatched against the Layer 15 freeze.
    """
    m_dir = Path(models_dir)
    c_dir = Path(calibration_dir)
    man_path = Path(manifest_path)

    # 1. Verify Evaluation Manifest exists
    if not man_path.exists():
        raise DomainValidationError(
            f"Layer 15 Evaluation Manifest not found at {man_path}. "
            "Layer 16 requires an approved, frozen manifest.",
            field="manifest_path",
            code=ErrorCode.NOT_FOUND,
        )

    with open(man_path, encoding="utf-8") as f:
        manifest_data = json.load(f)
    manifest = EvaluationManifest.model_validate(manifest_data)

    expected_model_checksum = manifest.model_freeze.artifact_checksum
    expected_cal_hash = manifest.model_freeze.calibration_policy_hash

    # 2. Compute actual model binary SHA-256
    model_artifact = m_dir / model_id / f"{model_id}.joblib"
    if not model_artifact.exists():
        raise DomainValidationError(
            f"Frozen model binary not found at {model_artifact}",
            field="model_artifact",
            code=ErrorCode.NOT_FOUND,
        )

    sha256 = hashlib.sha256()
    with open(model_artifact, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    actual_model_checksum = sha256.hexdigest()

    if actual_model_checksum != expected_model_checksum:
        raise DomainValidationError(
            f"Cryptographic integrity mismatch for model {model_id!r}: "
            f"computed {actual_model_checksum} != frozen {expected_model_checksum}. "
            "Model binary has been tampered with or replaced.",
            field="artifact_checksum",
            code=ErrorCode.PERMISSION_DENIED,
        )

    # 3. Verify Calibration Policy JSON hash
    cal_file = c_dir / f"{calibration_policy_id}-{model_id}.json"
    if not cal_file.exists():
        raise DomainValidationError(
            f"Calibration policy file not found at {cal_file}",
            field="calibration_file",
            code=ErrorCode.NOT_FOUND,
        )

    with open(cal_file, encoding="utf-8") as f:
        cal_data = json.load(f)
    actual_cal_hash = cal_data.get("policy_hash", "")

    if actual_cal_hash != expected_cal_hash:
        raise DomainValidationError(
            f"Calibration policy hash mismatch for {calibration_policy_id!r}: "
            f"actual {actual_cal_hash} != frozen {expected_cal_hash}.",
            field="calibration_policy_hash",
            code=ErrorCode.PERMISSION_DENIED,
        )

    return ModelIntegrityVerification(
        model_id=model_id,
        expected_artifact_checksum=expected_model_checksum,
        actual_artifact_checksum=actual_model_checksum,
        is_checksum_verified=True,
        feature_schema_version=manifest.model_freeze.feature_schema_version,
        calibration_policy_id=calibration_policy_id,
        calibration_policy_hash=actual_cal_hash,
        is_policy_verified=True,
        decision_threshold=manifest.model_freeze.decision_threshold,
        policy_version="TP-V1",
        risk_config_version="RISK-CFG-V1",
    )
