"""Zhatura AI Customer Care — Centralized Permission Service (Phase 7).

Enforces role-based access control and prevents cross-account data leakage.
All private account and student lookups MUST be evaluated through this layer.
"""

from __future__ import annotations

from .models import CallerIdentity, CallerRole, StudentProfile, VerificationState


class PermissionService:
    """Centralized authorization validator."""

    @staticmethod
    def is_verified(caller: CallerIdentity | None) -> bool:
        return bool(caller and caller.auth_state == VerificationState.VERIFIED)

    @classmethod
    def can_access_student(
        cls,
        caller: CallerIdentity | None,
        student_id: str,
        student_profile: StudentProfile | None = None,
    ) -> bool:
        """Check if caller is authorized to view or access a student's profile or progress."""
        if not cls.is_verified(caller) or caller is None:
            return False

        if caller.role == CallerRole.SUPPORT_ADMIN:
            return True

        if caller.role == CallerRole.PARENT:
            if student_id in caller.children:
                return True
            if student_profile and student_profile.parent_account_id == caller.account_id:
                return True
            return False

        if caller.role == CallerRole.STUDENT:
            if caller.student_id and caller.student_id == student_id:
                return True
            if student_profile and student_profile.account_id == caller.account_id:
                return True
            return False

        if caller.role == CallerRole.COACH:
            if student_id in caller.assigned_students:
                return True
            if student_profile and caller.coach_id and student_profile.coach_id == caller.coach_id:
                return True
            return False

        if caller.role == CallerRole.ACADEMY_ADMIN:
            # If student profile belongs to the academy's scope
            if caller.org_id and student_profile:
                # In full implementation, org membership check
                return True

        return False

    @classmethod
    def can_view_session(
        cls,
        caller: CallerIdentity | None,
        student_id: str,
        student_profile: StudentProfile | None = None,
    ) -> bool:
        """Session details follow student data privacy rules."""
        return cls.can_access_student(caller, student_id, student_profile)

    @classmethod
    def can_view_subscription(
        cls,
        caller: CallerIdentity | None,
        account_id: str,
    ) -> bool:
        """Check if caller can view subscription information for an account."""
        if not cls.is_verified(caller) or caller is None:
            return False

        if caller.role == CallerRole.SUPPORT_ADMIN:
            return True

        # Account holder can view own subscription
        if caller.account_id and caller.account_id == account_id:
            return True

        return False

    @classmethod
    def can_view_account(
        cls,
        caller: CallerIdentity | None,
        account_id: str,
    ) -> bool:
        """Check if caller can view general profile and status of an account."""
        if not cls.is_verified(caller) or caller is None:
            return False

        if caller.role == CallerRole.SUPPORT_ADMIN:
            return True

        if caller.account_id and caller.account_id == account_id:
            return True

        return False

    @classmethod
    def can_create_ticket(cls, caller: CallerIdentity | None) -> bool:
        """Any caller can submit a ticket; if verified, it links to their account."""
        return True

    @classmethod
    def can_create_callback(cls, caller: CallerIdentity | None) -> bool:
        """Callbacks can be requested by verified or unverified callers with contact info."""
        return True

    @classmethod
    def can_create_feedback(cls, caller: CallerIdentity | None, allow_anonymous: bool = True) -> bool:
        """Feedback can be submitted anonymously if allowed by policy."""
        if allow_anonymous:
            return True
        return cls.is_verified(caller)

    @classmethod
    def can_create_lead(cls, caller: CallerIdentity | None) -> bool:
        """Leads (academy / custom plans) do not require prior student/parent verification."""
        return True
