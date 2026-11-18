import unittest
from unittest.mock import patch
from modules import media,media_seek
class SeekTests(unittest.TestCase):
 def test_invalid_seek(self):
  for x in [-1,float('nan'),float('inf'),True,301]:
   with self.assertRaises(ValueError):media_seek.target_seconds(x,300)
 def test_stale_song_never_seeks(self):
  m=media.Module({'id':'music'});m.last_media={'track':1}
  with patch.object(media_seek,'seek') as action:
   with self.assertRaises(RuntimeError):m.action('seek',position=10,track=2)
   action.assert_not_called()
 def test_seek_waits_for_player(self):
  m=media.Module({'id':'music'});m.last_media={'track':1};m.poll=lambda:{'track':1,'position':42.5,'playing':True}
  with patch.object(media_seek,'seek',return_value=42),patch.object(media.time,'sleep'):
   self.assertTrue(m.action('seek',position=42,track=1)['playing'])
 def test_rejected_seek_no_fake_sync(self):
  m=media.Module({'id':'music'});m.last_media={'track':1};m.poll=lambda:{'track':1,'position':5,'playing':True}
  with patch.object(media_seek,'seek',return_value=42),patch.object(media.time,'sleep'):
   with self.assertRaises(RuntimeError):m.action('seek',position=42,track=1)
if __name__=='__main__':unittest.main()
