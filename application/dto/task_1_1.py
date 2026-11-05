"""Evidence for task 1.1, as plain typed data. Standard library only.

The reader produces these objects from Odoo; the grader consumes them. Many2one values are
named fields (``country``, ``action_id``), never positional pairs.
"""

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

# Odoo names this task reads. Shared by the grader (criteria text, decisions) and the reader (queries).
PIEROGI_NAME = "Pierogi Polska"
FILTER_NAME = "Українські компанії"
FILTER_MODEL = "res.partner"
SHARE_USER_NAME = "Марина"
UA_COUNTRY_CODE = "UA"
PARTNER_FIELDS = ("name", "is_company", "country_id", "lang", "active")


@dataclass(frozen=True)
class Retrieval(Generic[T]):
    """Outcome of one read. Exactly one state holds:

    - value:   the read succeeded and produced data (possibly an empty collection);
    - problem: Odoo answered, but the data is absent, ambiguous or was not queried;
    - error:   the read failed (access, network or unexpected value shape).

    A problem or an error is never represented as an empty successful value.
    """

    value: T | None = None
    problem: str | None = None
    error: str | None = None

    def __post_init__(self):
        if self.problem is not None and self.error is not None:
            raise ValueError("a retrieval has a problem or an error, not both")
        if self.value is not None and (self.problem is not None or self.error is not None):
            raise ValueError("a retrieval with a problem or error has no value")
        if self.value is None and self.problem is None and self.error is None:
            raise ValueError("a retrieval needs a value, a problem or an error")

    @classmethod
    def ok(cls, value):
        return cls(value=value)

    @classmethod
    def missing(cls, problem):
        return cls(problem=problem)

    @classmethod
    def failed(cls, error):
        return cls(error=error)


@dataclass(frozen=True)
class CountryRef:
    id: int
    code: str | None


@dataclass(frozen=True)
class PartnerRecord:
    id: int
    is_company: bool
    country: CountryRef | None
    lang: str | None


@dataclass(frozen=True)
class FilterRecord:
    id: int
    model_name: str | None  # ir.filters.model_id is a selection holding the model name
    domain_text: str | None
    user_ids: tuple[int, ...]
    is_default: bool | None
    active: bool | None
    action_id: int | None
    embedded_action_id: int | None


@dataclass(frozen=True)
class ContactsAction:
    id: int
    res_model: str


@dataclass(frozen=True)
class Task11Evidence:
    partner_fields: Retrieval[frozenset]  # names of fields present on res.partner
    ua_active_company_count: Retrieval[int]
    pierogi_partners: Retrieval[tuple]  # tuple[PartnerRecord, ...]
    filter_fields: Retrieval[frozenset]  # names of fields present on ir.filters
    filters: Retrieval[tuple]  # tuple[FilterRecord, ...], every record with the filter name, sorted by id
    ua_country: Retrieval[CountryRef]
    contacts_action: Retrieval[ContactsAction]
    share_user_id: Retrieval[int]
