# test_feishu_send.py
"""feishu_send 共享模块单测:重点覆盖限流重试逻辑与 webhook 加载。

运行: python -m unittest test_feishu_send
"""
import os
import tempfile
import unittest
from unittest.mock import patch

import feishu_send
from urllib.error import HTTPError


class FakeResp:
    """模拟 urllib 响应对象(支持 with 语法 + read)。"""
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body.encode("utf-8")


class TestSendFeishu(unittest.TestCase):
    def test_success_first_try(self):
        with patch("feishu_send.urllib.request.urlopen", return_value=FakeResp('{"StatusCode":0}')) as m, \
                patch("feishu_send.time.sleep"):
            code = feishu_send.send_feishu("hi", "http://hook")
        self.assertEqual(code, 0)
        m.assert_called_once()

    def test_retry_11232_then_success(self):
        responses = [
            FakeResp('{"code":11232,"msg":"frequency limited"}'),
            FakeResp('{"code":11232,"msg":"frequency limited"}'),
            FakeResp('{"code":0}'),
        ]
        with patch("feishu_send.urllib.request.urlopen", side_effect=responses) as m, \
                patch("feishu_send.time.sleep") as sleep:
            code = feishu_send.send_feishu("hi", "http://hook")
        self.assertEqual(code, 0)
        self.assertEqual(m.call_count, 3)
        # 退避间隔:0.5s → 1s
        self.assertEqual(sleep.call_args_list, [((0.5,),), ((1.0,),)])

    def test_retry_exhausted_raises(self):
        resp = FakeResp('{"code":11232,"msg":"frequency limited"}')
        with patch("feishu_send.urllib.request.urlopen", return_value=resp) as m, \
                patch("feishu_send.time.sleep"):
            with self.assertRaises(RuntimeError):
                feishu_send.send_feishu("hi", "http://hook")
        self.assertEqual(m.call_count, feishu_send.MAX_ATTEMPTS)

    def test_non_retryable_error_raises_immediately(self):
        resp = FakeResp('{"code":19021,"msg":"sign match fail"}')
        with patch("feishu_send.urllib.request.urlopen", return_value=resp) as m, \
                patch("feishu_send.time.sleep"):
            with self.assertRaises(RuntimeError):
                feishu_send.send_feishu("hi", "http://hook")
        m.assert_called_once()   # 不可重试,不重试

    def test_http_429_retried_then_success(self):
        with patch("feishu_send.urllib.request.urlopen", side_effect=[
                HTTPError("url", 429, "Too Many Requests", None, None),
                FakeResp('{"code":0}')]) as m, \
                patch("feishu_send.time.sleep"):
            code = feishu_send.send_feishu("hi", "http://hook")
        self.assertEqual(code, 0)
        self.assertEqual(m.call_count, 2)

    def test_http_500_retried(self):
        with patch("feishu_send.urllib.request.urlopen", side_effect=[
                HTTPError("url", 500, "Internal", None, None),
                HTTPError("url", 500, "Internal", None, None),
                HTTPError("url", 500, "Internal", None, None)]) as m, \
                patch("feishu_send.time.sleep"):
            with self.assertRaises(HTTPError):
                feishu_send.send_feishu("hi", "http://hook")
        self.assertEqual(m.call_count, feishu_send.MAX_ATTEMPTS)

    def test_network_error_retried(self):
        from urllib.error import URLError
        with patch("feishu_send.urllib.request.urlopen", side_effect=[
                URLError("conn refused"),
                FakeResp('{"code":0}')]) as m, \
                patch("feishu_send.time.sleep"):
            code = feishu_send.send_feishu("hi", "http://hook")
        self.assertEqual(code, 0)
        self.assertEqual(m.call_count, 2)


class TestLoadWebhook(unittest.TestCase):
    def test_env_var_priority(self):
        with patch.dict("os.environ", {"FEISHU_WEBHOOK": "http://env-hook"}):
            self.assertEqual(feishu_send.load_webhook(), "http://env-hook")

    def test_read_project_env_file(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, ".env"), "w", encoding="utf-8") as f:
                f.write('# comment\nFEISHU_WEBHOOK="http://from-file"\nOTHER=x\n')
            with patch.dict("os.environ", {}, clear=True):
                self.assertEqual(feishu_send.load_webhook(env_dir=d), "http://from-file")

    def test_missing_env_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.dict("os.environ", {}, clear=True):
                self.assertEqual(feishu_send.load_webhook(env_dir=d), "")


if __name__ == "__main__":
    unittest.main()
