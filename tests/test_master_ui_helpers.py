import os
import unittest

from master_ui import subprocess_environment


class MasterUiHelperTests(unittest.TestCase):
    def test_subprocess_environment_forces_safe_python_output_encoding(self) -> None:
        env = subprocess_environment()

        self.assertEqual(env["PYTHONIOENCODING"], "utf-8:backslashreplace")
        self.assertEqual(env.get("PATH"), os.environ.get("PATH"))


if __name__ == "__main__":
    unittest.main()
