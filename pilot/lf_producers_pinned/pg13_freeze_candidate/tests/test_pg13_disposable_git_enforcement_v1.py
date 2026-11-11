"""Execute actual Git mutations against a disposable protected bare repository."""
import subprocess
import sys
import unittest
from pathlib import Path

class GitFreezeMutation(unittest.TestCase):
    def test_force_push_normal_push_delete_and_recreate_are_all_blocked(self):
        script=Path(__file__).resolve().parents[1]/"tools"/"pg13_disposable_git_mutation_test_v1.py"
        p=subprocess.run([sys.executable,str(script)],capture_output=True,
                         text=True,timeout=30,check=False)
        self.assertEqual(p.returncode,0,p.stderr+"\n"+p.stdout)
        for case in ("FORCE_PUSH","NORMAL_FAST_FORWARD","DELETE",
                     "RECREATE_DIFFERENT_SHA","DELETE_ANNOTATED_TAG"):
            with self.subTest(attack=case):
                self.assertIn("PG13_C3_"+case+"_BLOCK=PASS",p.stdout)
                self.assertIn("PG13_C3_"+case+"_COMMAND_EXIT_NONZERO=TRUE",p.stdout)
                self.assertIn("PG13_C3_"+case+"_REFS_UNCHANGED=TRUE",p.stdout)
        self.assertIn("PG13_C3_RECEIVE_DENY_DELETES=TRUE",p.stdout)
        self.assertIn("PG13_C3_PRE_RECEIVE_IMMUTABILITY_HOOK=TRUE",p.stdout)
        self.assertIn("PG13_C3_PRODUCTION_FREEZE_VERIFIED=FALSE",p.stdout)

if __name__=="__main__":
    unittest.main()
