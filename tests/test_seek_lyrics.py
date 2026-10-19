import unittest
from unittest.mock import patch
from modules import media,media_seek
class SeekAndLyricsTests(unittest.TestCase):
 def test_title_variants(self):self.assertIn('Mayonaka No Door',media._title_queries('Mayonaka No Door~stay with Me 2024'))
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
 def test_japanese_alias_same_artist(self):
  def lookup(kind,params):
   if kind=='search' and params['q']=='Mayonaka No Door':return [{'id':1,'trackName':'Mayonaka no Door / Stay With Me','artistName':'Miki Matsubara','duration':293,'syncedLyrics':'[00:01.00]夜のうた'},{'id':2,'trackName':'Mayonaka no Door','artistName':'Other Cover','duration':292,'syncedLyrics':'[00:01.00]wrong'}]
   return [] if kind=='search' else None
  with patch.object(media,'_lrclib',side_effect=lookup):
   result=media._fetch_lrclib('Mayonaka No Door~stay with Me 2024','Miki Matsubara','',292.667)
   self.assertEqual(result['synced'][0][1],'夜のうた')
 def test_translation_not_reordered(self):
  with patch.object(media,'_fetch_lrclib',return_value={'synced':[[1,'Original','原文']] } ):
   self.assertEqual(media.fetch_lyrics('Song','Artist','',300)['synced'][0][1],'Original')
if __name__=='__main__':unittest.main()
