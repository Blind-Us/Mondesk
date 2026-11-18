import unittest
from unittest.mock import patch
import displays

class DisplayTests(unittest.TestCase):
    def setUp(self):
        self.screens=[dict(name='DISPLAY1',primary=True,current=dict(w=2560,h=1600,hz=240),modes=[dict(w=960,h=640)]),dict(name='DISPLAY2',primary=False,current=dict(w=1920,h=1080,hz=60),modes=[dict(w=960,h=640),dict(w=1920,h=1080)])]
        # the same pretend screens on every system (Windows reads them one way, Linux another)
        self.patcher=patch.object(displays,'_windows',return_value=self.screens)
        self.patcher.start()
        self.linux=patch.object(displays,'_linux',return_value=self.screens)
        self.linux.start()
        self.applier=patch.object(displays,'_apply',return_value=dict(ok=True,message='ok'))
        self.apply=self.applier.start()
    def tearDown(self):
        for d in displays._pending.values(): d['timer'].cancel()
        displays._pending.clear()
        self.patcher.stop();self.linux.stop();self.applier.stop()
    def test_primary_blocked(self):
        self.assertFalse(displays.set_mode('DISPLAY1',960,640,'try')['ok'])
        self.apply.assert_not_called()
    def test_unsupported_blocked(self):
        self.assertFalse(displays.set_mode('DISPLAY2',999,999,'try')['ok'])
    def test_test_does_not_change(self):
        self.assertTrue(displays.set_mode('DISPLAY2',960,640,'test')['ok'])
        self.apply.assert_called_once_with('DISPLAY2',dict(w=960,h=640),test=True)
    def test_revert_restores_exact_original(self):
        trial=displays.set_mode('DISPLAY2',960,640,'try',timeout=60)
        result=displays.set_mode('DISPLAY2',step='revert',change_id=trial['change_id'])
        self.assertTrue(result['ok'])
        self.apply.assert_called_with('DISPLAY2',dict(w=1920,h=1080,hz=60))
    def test_expired_trial_cannot_reapply(self):
        trial=displays.set_mode('DISPLAY2',960,640,'try',timeout=60)
        displays._expire('DISPLAY2',trial['change_id'])
        self.apply.reset_mock()
        self.assertFalse(displays.set_mode('DISPLAY2',960,640,'keep',change_id=trial['change_id'])['ok'])
        self.apply.assert_not_called()
    def test_stale_ticket_cannot_keep(self):
        trial=displays.set_mode('DISPLAY2',960,640,'try',timeout=60)
        self.assertFalse(displays.set_mode('DISPLAY2',step='keep',change_id='wrong')['ok'])
        self.assertTrue(displays.set_mode('DISPLAY2',step='keep',change_id=trial['change_id'])['ok'])

if __name__=='__main__':unittest.main()
