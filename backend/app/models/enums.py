import enum


class Role(enum.StrEnum):
    """Org membership roles, ordered from most to least privileged."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"

    @classmethod
    def rank(cls, role: "Role") -> int:
        """Higher number = more privilege. Used by require_role checks."""
        return {"owner": 3, "admin": 2, "member": 1, "viewer": 0}[role.value]
