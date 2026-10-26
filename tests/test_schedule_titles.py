"""Schedule labels must represent the same instant in their configured timezone."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest


spec = importlib.util.spec_from_file_location('schedule_title_helpers',
    Path(__file__).resolve().parents[1] / 'whatsapp_messaging/messaging/naming.py')
naming = importlib.util.module_from_spec(spec)
previous_frappe = sys.modules.get('frappe')
sys.modules['frappe'] = ModuleType('frappe')
try:
    spec.loader.exec_module(naming)
finally:
    if previous_frappe is None:
        sys.modules.pop('frappe', None)
    else:
        sys.modules['frappe'] = previous_frappe


class TestScheduleTitles(unittest.TestCase):
    def test_india_schedule_title_uses_local_time(self):
        doc = SimpleNamespace(doctype='WhatsApp Schedule', rule='Welcome', one_shot=1,
            next_due_at='2026-10-24 04:40:15', timezone='Asia/Calcutta')
        self.assertEqual(naming.record_title(doc), 'Welcome · Once · 2026-10-24 10:10:15 · Asia/Calcutta')

    def test_daylight_saving_uses_the_offset_at_the_due_date(self):
        self.assertEqual(naming.schedule_local_time('2026-07-01 14:00:00', 'America/New_York'),
                         '2026-07-01 10:00:00')
        self.assertEqual(naming.schedule_local_time('2026-12-01 14:00:00', 'America/New_York'),
                         '2026-12-01 09:00:00')

    def test_recurring_title_preserves_its_local_cron_expression(self):
        doc = SimpleNamespace(doctype='WhatsApp Schedule', rule='Welcome', one_shot=0,
            next_due_at='2026-10-24 04:40:15', timezone='Asia/Calcutta', cron_expression='0 10 * * *')
        self.assertEqual(naming.record_title(doc), 'Welcome · Recurring · 0 10 * * * · Asia/Calcutta')
