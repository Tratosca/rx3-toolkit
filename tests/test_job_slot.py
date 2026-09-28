# SPDX-License-Identifier: MPL-2.0
"""A hidden progress UI cannot release the server's single job slot."""
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest
from app.ui.bridge import Bridge
from app.localization import LocalizedError

class JobSlotTests(unittest.TestCase):
    def test_concurrent_launches_claim_one_slot(self):
        bridge=Bridge()
        barrier=threading.Barrier(8)
        def claim(index):
            barrier.wait()
            try:
                bridge._claim('stems', 'test')
                return True
            except LocalizedError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(claim,range(8))),1)
        self.assertEqual(bridge.job_status()['value']['state'],'running')
        for kind in ('stems','mod','samples','key','runtime'):
            with self.assertRaises(LocalizedError):
                bridge._claim(kind,'test')
        bridge._settle('done','test')
        bridge._claim('stems','next')
        self.assertEqual(bridge.job_status()['value']['message'],'next')
