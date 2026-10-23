"""Add readable titles to old rows without changing their names or timestamps."""
from whatsapp_messaging.messaging.naming import backfill_titles


def execute():
    backfill_titles()
