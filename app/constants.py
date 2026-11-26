"""Shared role, designated position, and dashboard tab constants."""

DESIGNATED_POSITIONS = [
    ('ceo', 'CEO'),
    ('proprietor', 'Proprietor'),
    ('agm', 'AGM'),
    ('operation_manager', 'Operation Manager'),
    ('admin_in_charge', 'Admin In Charge'),
    ('hr_manager', 'HR Manager'),
]

DESIGNATED_POSITION_KEYS = [key for key, _ in DESIGNATED_POSITIONS]
DESIGNATED_POSITION_LABELS = dict(DESIGNATED_POSITIONS)

DASHBOARD_TABS = [
    ('ceo', 'CEO Schedule'),
    ('proprietor', 'Proprietor Schedule'),
    ('agm', 'AGM Schedule'),
    ('operation_manager', 'Operation Manager Schedule'),
    ('admin_in_charge', 'Admin In Charge Schedule'),
    ('hr_manager', 'HR Manager Schedule'),
    ('combined', 'Combined Schedule'),
    ('mine', 'My Schedule'),
]

DASHBOARD_TAB_LABELS = dict(DASHBOARD_TABS)

NEW_UNIQUE_ROLES = (
    'AGM',
    'Operation Manager',
    'Admin In Charge',
    'HR Manager',
)

UNIQUE_ROLES = (
    'Admin',
    'Proprietor',
    'AGM',
    'Operation Manager',
    'Admin In Charge',
    'HR Manager',
)

UNIQUE_ROLES_LOWER = {r.lower() for r in UNIQUE_ROLES}
NEW_UNIQUE_ROLES_LOWER = {r.lower() for r in NEW_UNIQUE_ROLES}

ALLOWED_REGISTRATION_ROLES = (
    'Employee',
    'Personal Assistant',
    'Senior Assistant',
    'AGM',
    'Operation Manager',
    'Admin In Charge',
    'HR Manager',
    'Proprietor',
    'Admin',
)

STAFF_MANAGER_ROLES = {
    'Personal Assistant',
    'Senior Assistant',
    'Admin',
}

_ROLE_TO_POSITION = {
    'ceo': 'ceo',
    'proprietor': 'proprietor',
    'agm': 'agm',
    'operation manager': 'operation_manager',
    'admin in charge': 'admin_in_charge',
    'hr manager': 'hr_manager',
}

_POSITION_TO_ROLE = {
    'ceo': 'CEO',
    'proprietor': 'Proprietor',
    'agm': 'AGM',
    'operation_manager': 'Operation Manager',
    'admin_in_charge': 'Admin In Charge',
    'hr_manager': 'HR Manager',
}


def role_to_position_key(role_name: str | None) -> str | None:
    """Map a user's role string to its canonical designated position key, if any."""
    if not role_name:
        return None
    normalized = ' '.join(role_name.strip().lower().split())
    if normalized in _ROLE_TO_POSITION:
        return _ROLE_TO_POSITION[normalized]
    if 'ceo' in normalized and 'in charge' not in normalized:
        return 'ceo'
    return None


def position_key_to_role(position_key: str | None) -> str | None:
    """Map a designated position key back to its canonical role display name."""
    if not position_key:
        return None
    return _POSITION_TO_ROLE.get(position_key.strip().lower())
