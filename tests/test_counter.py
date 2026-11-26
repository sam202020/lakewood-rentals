import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build  # noqa: E402


class CounterCode(unittest.TestCase):
    def code(self, text):
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "analytics.json"
            f.write_text(text)
            return build.counter_code(f)

    def test_only_a_plain_site_code_turns_counting_on(self):
        self.assertEqual(self.code(json.dumps({"goatcounter": " LakewoodRentals "})), "lakewoodrentals")
        for bad in ("", "https://x.goatcounter.com", "a b", 'x"><script>', "-x"):
            self.assertEqual(self.code(json.dumps({"goatcounter": bad})), "", bad)
        self.assertEqual(self.code("not json"), "")
        self.assertEqual(build.counter_code(pathlib.Path("/no/such/file")), "")

    def test_the_checked_in_setting_is_valid(self):
        value = json.loads((ROOT / "data" / "analytics.json").read_text())["goatcounter"]
        self.assertEqual(build.counter_code(), value.strip().lower())


if __name__ == "__main__":
    unittest.main()
