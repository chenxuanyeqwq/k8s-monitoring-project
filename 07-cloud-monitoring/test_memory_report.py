# test_memory_report.py
import unittest
from memory_report import parse_meminfo, mem_report

SAMPLE = "MemTotal:       2048000 kB\nMemFree:        102400 kB\nMemAvailable:    819200 kB\n"

class TestMem(unittest.TestCase):
    def test_parse_meminfo(self):
        m = parse_meminfo(SAMPLE)
        self.assertEqual(m["MemTotal"], 2048000 * 1024)
        self.assertEqual(m["MemAvailable"], 819200 * 1024)

    def test_mem_report_pct(self):
        r = mem_report(parse_meminfo(SAMPLE))
        # 2000MiB - 800MiB = 1200MiB ≈ 1.17 GiB (kB=1024B, GB=GiB)
        self.assertAlmostEqual(r["used_gb"], 1.17, delta=0.01)
        self.assertAlmostEqual(r["pct"], 60.0, delta=0.1)

if __name__ == "__main__":
    unittest.main()
