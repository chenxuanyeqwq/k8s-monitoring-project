import unittest
from service_probe import apply_probe_result


class ApplyProbeResultTest(unittest.TestCase):
    def test_first_fail_is_warn(self):
        rec = {"fail_count": 0, "status": "up"}
        new, event = apply_probe_result(rec, False, "连接失败", 3)
        self.assertEqual(event, "warn")
        self.assertEqual(new["fail_count"], 1)

    def test_third_fail_triggers_alert(self):
        rec = {"fail_count": 2, "status": "up"}
        new, event = apply_probe_result(rec, False, "连接失败", 3)
        self.assertEqual(event, "alert")
        self.assertEqual(new["status"], "down")

    def test_down_does_not_repeat_alert(self):
        rec = {"fail_count": 3, "status": "down"}
        new, event = apply_probe_result(rec, False, "连接失败", 3)
        self.assertEqual(event, "warn")  # 已 down，只累加计数，不重复告警

    def test_success_resets_count(self):
        rec = {"fail_count": 2, "status": "up"}
        new, event = apply_probe_result(rec, True, "", 3)
        self.assertEqual(event, "ok")
        self.assertEqual(new["fail_count"], 0)

    def test_recover_from_down(self):
        rec = {"fail_count": 3, "status": "down"}
        new, event = apply_probe_result(rec, True, "", 3)
        self.assertEqual(event, "recover")
        self.assertEqual(new["status"], "up")
        self.assertEqual(new["fail_count"], 0)

    def test_below_threshold_stays_up(self):
        rec = {"fail_count": 1, "status": "up"}
        new, event = apply_probe_result(rec, False, "HTTP 500", 3)
        self.assertEqual(event, "warn")
        self.assertEqual(new["status"], "up")


if __name__ == "__main__":
    unittest.main()
