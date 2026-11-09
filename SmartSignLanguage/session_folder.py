"""Name the outer session folder; leave all data files and schemas unchanged."""
from datetime import datetime, timedelta, timezone
import re


def user_folder(user):
    """Use a short outer folder name, e.g. U01 -> U1, without changing metadata."""
    if re.fullmatch(r'U[0-9]+', user):
        return 'U' + str(int(user[1:]))
    return re.sub(r'[^A-Za-z0-9_-]', '_', user)


def folder_name(sid, user, labels):
    local = datetime.strptime(sid.split('_')[0], '%Y%m%dT%H%M%SZ').replace(
        tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=7)))
    def safe(value):
        return re.sub(r'[^A-Za-z0-9_-]', '_', value)
    label_text = safe('-'.join(labels))[:60] or 'CHUA_CO_NHAN'
    return f"{local:%Y-%m-%d_%H-%M-%S}__{safe(user)[:40]}__{label_text}__{safe(sid.split('_')[-1])}"
