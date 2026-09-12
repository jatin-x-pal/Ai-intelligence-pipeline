import datetime
from datetime import timedelta


def is_fresh(publication_dt: datetime.datetime | None, reference: datetime.datetime | None = None, max_age: timedelta = timedelta(hours=24)) -> bool:
    """Return True if the publication datetime is within max_age of reference.
    Both datetimes are treated as UTC aware. None is considered not fresh.
    """
    if publication_dt is None:
        return False
    if reference is None:
        reference = datetime.datetime.now(datetime.UTC)
    pub = publication_dt.astimezone(datetime.UTC)
    ref = reference.astimezone(datetime.UTC)
    return (ref - pub) <= max_age
