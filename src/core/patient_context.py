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
    tandplejeplan: bool = False
    regionstilsagn: bool = False

    # Collected during initialization checks
    primary_clinic_data: list = field(default_factory=list)
    extern_clinic_data: list = field(default_factory=list)
    administrative_note: list = field(default_factory=list)

    # Derived during process
    is_under_16: bool = False
    discharge_document_filename: str = ""

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
        return cls(
            patient_cpr=item_data.get("cpr", "").replace("-", ""),
            patient_name=item_data.get("name", ""),
            request_number=item_data.get("requestNumberServiceNow", ""),
            tandplejeplan=item_data.get("tandplejeplan", False),
            regionstilsagn=item_data.get("regionstilsagn", False),
        )
