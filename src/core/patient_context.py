# src/core/patient_context.py

"""Typed container for data collected during initialization.

Usage:
    # In process_item.py:
    ctx = run_initialization_checks(runner, app, db, item_data)
    update_patient_info(runner, app, ctx)
    create_documents(runner, app, ctx)
    send_via_edi_portal(runner, app, ctx)
"""

from dataclasses import dataclass, field

from src.helpers.cpr_utils import is_under_16


@dataclass
class PatientContext:
    """All data needed to process a single patient item.

    Built during initialization checks, then passed to every
    subsequent step. Immutable after initialization — steps read
    from it but don't modify it.
    """

    # From the work queue item
    patient_cpr: str = ""
    patient_name: str = ""
    request_number: str = ""
    clinic_name: str = ""
    tandplejeplan: bool = False
    regionstilsagn: bool = False

    # Collected during initialization checks
    primary_clinic_data: list = field(default_factory=list)
    extern_clinic_data: list = field(default_factory=list)
    administrative_note: list = field(default_factory=list)

    # Derived during process
    is_under_16: bool = False
    discharge_document_filename: str | None = None

    # Romexis specific data
    romexis_zip_path: str | None = None
    romexis_zip_filename: str | None = None

    # EDI Portal specific data
    edi_portal_file_paths: str | None = None
    edi_receipt_path: str | None = None

    # Dashboard
    # process_name: str | None = None

    @property
    def contractor_id(self) -> str | None:
        """Get the contractor ID from extern clinic data."""
        if self.extern_clinic_data:
            return self.extern_clinic_data[0].get("contractorId")
        return None

    @property
    def clinic_phone_number(self) -> str | None:
        """Get the phone number from extern clinic data."""
        if self.extern_clinic_data:
            return self.extern_clinic_data[0].get("phoneNumber")
        return None

    @property
    def patient_status(self) -> str | None:
        """Get the patient's current status."""
        if self.primary_clinic_data:
            return self.primary_clinic_data[0].get("patientStatus")
        return None

    @property
    def preferred_clinic_name(self) -> str | None:
        """Get the preferred dental clinic name."""
        if self.primary_clinic_data:
            return self.primary_clinic_data[0].get("preferredDentalClinicName")
        return None

    @property
    def is_preferred_clinic_locked(self) -> bool:
        """Check if the preferred clinic field is locked."""
        if self.primary_clinic_data:
            return self.primary_clinic_data[0].get(
                "isPreferredDentalClinicLocked", False
            )
        return False

    @property
    def clinician_name(self) -> str | None:
        """Get the current clinician name."""
        if self.primary_clinic_data:
            return self.primary_clinic_data[0].get("clinicianName")
        return None

    @property
    def journal_note_text(self) -> str | None:
        """Get the administrative note text."""
        if self.administrative_note:
            return self.administrative_note[0].get("Beskrivelse")
        return None

    @property
    def process_name(self) -> str | None:
        """Get the process name"""
        if self.process_name:
            return ""
        return None

    @classmethod
    def from_item_data(cls, item_data: dict) -> "PatientContext":
        """Create a PatientContext from work queue item data.

        Args:
            item_data: The raw dictionary from the work queue item.

        Returns:
            A PatientContext with queue item fields populated.
            Initialization data fields are still empty — they get
            filled by run_initialization_checks().
        """
        raw_cpr = item_data.get("patient_cpr") or item_data.get("cpr", "")
        cleaned_cpr = raw_cpr.replace("-", "")

        if not cleaned_cpr:
            raise ValueError(
                "Missing CPR in item_data (expected 'patient_cpr' or 'cpr')"
            )

        patient_name = item_data.get("patient_name") or item_data.get("name", "")

        return cls(
            patient_cpr=cleaned_cpr,
            patient_name=patient_name,
            request_number=item_data.get("requestNumberServiceNow", ""),
            tandplejeplan=item_data.get("tandplejeplan", False),
            regionstilsagn=item_data.get("regionstilsagn", False),
            clinic_name=item_data.get("klinik_navn", False),
            is_under_16=is_under_16(cleaned_cpr) if cleaned_cpr else False,
        )
