"""Cryptographic lockbox and container for temporal splits (Layer 8).

Governed by:
- ACCEPTANCE_GATES.md §1 (G-8, Unseen data / No snooping)
- DATA_AND_PERFORMANCE_POLICY.md §7 (Evaluation Hygiene)
- Layer 8 Gate: Lock final-test identifiers and prevent routine tuning code
  from loading final-test labels/results.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from finpilot.schemas.errors import DomainValidationError, ErrorCode

from .models import PartitionType, SplitManifest, TradePolicyLabel
from .split_manager import FinalTestLockedError


class FinalTestLockbox:
    """Enforces strict isolation of the LOCKED_FINAL_TEST partition against routine access.

    Guarantees:
    1. Routine access to TRAIN, DEV, CALIBRATION, and THRESHOLD partitions is unrestricted.
    2. Any attempt to load LOCKED_FINAL_TEST without a cryptographically valid authorization token
       raises FinalTestLockedError.
    3. Tamper verification: Validates that the SHA-256 hash of loaded test sample IDs matches
       the manifest's locked_final_test_hash.
    """

    def __init__(
        self,
        manifest: SplitManifest,
        partitions: dict[PartitionType, list[TradePolicyLabel]],
    ) -> None:
        self.manifest = manifest
        self._partitions = partitions

    @property
    def manifest_id(self) -> str:
        return self.manifest.manifest_id

    @property
    def is_locked(self) -> bool:
        return self.manifest.is_final_test_locked

    def generate_unlock_token(self) -> str:
        """Generate the required token to intentionally unseal the final test set."""
        return f"UNSEAL_FINAL_TEST_{self.manifest.locked_final_test_hash[:12]}"

    def get_train_samples(self) -> list[TradePolicyLabel]:
        """Access TRAIN partition."""
        return self._partitions.get(PartitionType.TRAIN, [])

    def get_dev_samples(self) -> list[TradePolicyLabel]:
        """Access DEV_MODEL_SELECTION partition."""
        return self._partitions.get(PartitionType.DEV_MODEL_SELECTION, [])

    def get_calibration_samples(self) -> list[TradePolicyLabel]:
        """Access CALIBRATION partition."""
        return self._partitions.get(PartitionType.CALIBRATION, [])

    def get_threshold_samples(self) -> list[TradePolicyLabel]:
        """Access THRESHOLD_SELECTION partition."""
        return self._partitions.get(PartitionType.THRESHOLD_SELECTION, [])

    def get_final_test_samples(self, unlock_token: str | None = None) -> list[TradePolicyLabel]:
        """Access LOCKED_FINAL_TEST partition. Requires exact unlock_token."""
        expected_token = self.generate_unlock_token()
        if unlock_token != expected_token:
            raise FinalTestLockedError(
                "Access to LOCKED_FINAL_TEST is blocked to prevent data snooping. "
                "Tuning algorithms must never evaluate against final test data. "
                "Provide unlock_token only for final evaluation."
            )

        test_samples = self._partitions.get(PartitionType.LOCKED_FINAL_TEST, [])
        self.verify_integrity(test_samples)
        return test_samples

    def verify_integrity(self, test_samples: list[TradePolicyLabel] | None = None) -> bool:
        """Verify that final test samples have not been modified or corrupted."""
        samples = test_samples or self._partitions.get(PartitionType.LOCKED_FINAL_TEST, [])
        sample_ids = sorted(x.sample_id for x in samples)
        computed_hash = hashlib.sha256(",".join(sample_ids).encode("utf-8")).hexdigest()

        if computed_hash != self.manifest.locked_final_test_hash:
            raise DomainValidationError(
                f"Integrity check failed: computed hash {computed_hash} does not match "
                f"manifest locked hash {self.manifest.locked_final_test_hash}",
                field="locked_final_test_hash",
                code=ErrorCode.VALIDATION_ERROR,
            )
        return True

    def save_manifest(self, filepath: str | Path) -> None:
        """Save the split manifest to JSON file."""
        target_path = Path(filepath)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_dict = self.manifest.model_dump(mode="json")
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(manifest_dict, f, indent=2, sort_keys=True)
