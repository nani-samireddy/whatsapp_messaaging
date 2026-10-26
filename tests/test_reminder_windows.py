from datetime import date, datetime, timezone
import unittest

from whatsapp_messaging.messaging.reminders import date_window, matches, daily_cron


class TestReminderWindows(unittest.TestCase):
    def test_three_day_sequence_includes_two_days_before_through_due_date(self):
        due='2026-10-27'
        selected=[]
        for day in range(23,29):
            instant=datetime(2026,10,day,3,30,tzinfo=timezone.utc)
            if matches(due,instant,'Asia/Calcutta',2):selected.append(day)
        self.assertEqual(selected,[25,26,27])

    def test_daily_window_excludes_missing_past_and_later_dates(self):
        now=datetime(2026,10,25,3,30)
        for value in (None,'','2026-10-24','2026-10-28'):
            self.assertFalse(matches(value,now,'Asia/Calcutta',2))
        for value in ('2026-10-25','2026-10-26','2026-10-27'):
            self.assertTrue(matches(value,now,'Asia/Calcutta',2))

    def test_window_uses_the_campaign_timezone_at_midnight(self):
        now=datetime(2026,10,24,20,0)
        self.assertEqual(date_window(now,'Asia/Calcutta',2),(date(2026,10,25),date(2026,10,27)))
        self.assertEqual(date_window(now,'America/New_York',2),(date(2026,10,24),date(2026,10,26)))

    def test_dst_does_not_change_daily_local_time(self):
        self.assertEqual(daily_cron('09:00:00'),'0 9 * * *')
        self.assertEqual(date_window(datetime(2026,11,1,14,0),'America/New_York',0),
                         (date(2026,11,1),date(2026,11,1)))

    def test_invalid_configuration_is_rejected(self):
        for days in (-1,31,2.5):
            with self.assertRaises(ValueError):date_window(datetime(2026,10,25),'UTC',days)
        for value in ('24:00','09:60','09:00:01','bad'):
            with self.assertRaises(ValueError):daily_cron(value)
