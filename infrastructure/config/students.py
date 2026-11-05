"""Student configuration: load and validate the JSON file, select students, resolve credential references.

The JSON holds only names of environment variables, never credentials. Validation happens before any
connection is made. Credentials are resolved only for the students that were selected.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

# Student ids become directory names, so they are identifiers: no separators, dots or spaces.
SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
ENV_VAR_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
REQUIRED_FIELDS = ("id", "url", "db", "login_env", "password_env")
OPTIONAL_FIELDS = ("share_user_id", "share_user_login", "contacts_action_xmlid")


class ConfigError(Exception):
    """The configuration is invalid, or a selection or credential reference cannot be satisfied."""


@dataclass(frozen=True)
class StudentConfig:
    id: str
    url: str
    db: str
    login_env: str
    password_env: str
    share_user_id: int | None = None  # takes precedence over share_user_login, as in single-database mode
    share_user_login: str | None = None
    contacts_action_xmlid: str | None = None


def load_students(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ConfigError(f"cannot read configuration file {path}: {type(error).__name__}") from error
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigError(f"{path} is not valid JSON (line {error.lineno}, column {error.colno})") from error
    return parse_students(data)


def parse_students(data):
    if not isinstance(data, dict) or set(data) != {"students"}:
        raise ConfigError('the configuration must be an object with exactly one key, "students"')
    entries = data["students"]
    if not isinstance(entries, list) or not entries:
        raise ConfigError('"students" must be a non-empty list')

    students = tuple(_parse_student(entry, index) for index, entry in enumerate(entries))
    seen = set()
    for student in students:
        if student.id in seen:
            raise ConfigError(f"duplicate student id {student.id!r}")
        seen.add(student.id)
    return students


def select_students(students, student_id=None, select_all=False):
    """Return exactly the requested students. Never falls back to another student."""
    if select_all == (student_id is not None):
        raise ConfigError("select exactly one of a single student id or all students")
    if select_all:
        return tuple(students)
    for student in students:
        if student.id == student_id:
            return (student,)
    configured = ", ".join(student.id for student in students)
    raise ConfigError(f"unknown student id {student_id!r}; configured ids: {configured}")


def resolve_credentials(student, environ):
    """Return (login, password) from the environment. Names missing variables, never values."""
    login = environ.get(student.login_env, "")
    password = environ.get(student.password_env, "")
    missing = [name for name, value in ((student.login_env, login), (student.password_env, password)) if not value]
    if missing:
        raise ConfigError(f"student {student.id}: environment variable(s) not set: {', '.join(missing)}")
    return login, password


def _parse_student(entry, index):
    where = f"students[{index}]"
    if not isinstance(entry, dict):
        raise ConfigError(f"{where} must be an object")
    missing = [name for name in REQUIRED_FIELDS if name not in entry]
    if missing:
        raise ConfigError(f"{where}: missing required field(s): {', '.join(missing)}")
    unknown = sorted(set(entry) - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS))
    if unknown:
        raise ConfigError(f"{where}: unknown field(s): {', '.join(unknown)}")

    student_id = _text(entry, "id", where)
    if not SAFE_IDENTIFIER.fullmatch(student_id):
        raise ConfigError(f"{where}: id must be 1-64 letters, digits, '_' or '-', starting with a letter or digit")
    where = f"student {student_id}"

    share_user_id = entry.get("share_user_id")
    if share_user_id is not None and (isinstance(share_user_id, bool) or not isinstance(share_user_id, int)
                                      or share_user_id <= 0):
        raise ConfigError(f"{where}: share_user_id must be a positive integer")
    xmlid = entry.get("contacts_action_xmlid")
    if xmlid is not None:
        module, _, name = _text(entry, "contacts_action_xmlid", where).partition(".")
        if not module or not name:
            raise ConfigError(f"{where}: contacts_action_xmlid must look like module.name")

    return StudentConfig(
        id=student_id,
        url=_https_url(_text(entry, "url", where), where),
        db=_text(entry, "db", where),
        login_env=_env_name(_text(entry, "login_env", where), "login_env", where),
        password_env=_env_name(_text(entry, "password_env", where), "password_env", where),
        share_user_id=share_user_id,
        share_user_login=_text(entry, "share_user_login", where) if "share_user_login" in entry else None,
        contacts_action_xmlid=xmlid,
    )


def _text(entry, key, where):
    value = entry.get(key)
    if not isinstance(value, str) or not value or value != value.strip():
        raise ConfigError(f"{where}: {key} must be a non-empty string without surrounding whitespace")
    return value


def _env_name(value, key, where):
    if not ENV_VAR_NAME.fullmatch(value):
        raise ConfigError(f"{where}: {key} must be an environment variable name, not a value")
    return value


def _https_url(value, where):
    try:
        parts = urlsplit(value)
        parts.port  # raises ValueError for an invalid port
    except ValueError as error:
        raise ConfigError(f"{where}: url is not valid") from error
    if (parts.scheme != "https" or not parts.hostname or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment or any(char.isspace() for char in value)):
        raise ConfigError(f"{where}: url must be an https URL with a host and no credentials, query or fragment")
    return value.rstrip("/")
