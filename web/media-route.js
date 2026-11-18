/* What tapping the music card opens. Source routing is explicit: absence of video data
   never means Apple Music. Video is mirrored from the playing tab, so any site's <video>
   works (YouTube, YouTube Music, other connected tabs) and the tab keeps playing. */
(() => {
  function resolve(data = {}) {
    if (!data.browser_bridge) return {kind: 'unavailable', message: '目前只有系統播放資訊，尚未連接影片或原生歌詞資料。'};
    if (data.video) return {kind: 'video'};
    if (data.source === 'Apple Music') return {kind: 'lyrics'};
    return {kind: 'unavailable', message: '此來源目前沒有可開啟的歌詞或影片。'};
  }
  // The fullscreen page is already open: which view should it show now? A video that starts
  // while lyrics are up (YouTube, an Apple Music music video) takes over the screen; when the
  // video ends the page goes back to lyrics.
  function follow(view, data = {}) {
    if (view === 'lyrics' && resolve(data).kind === 'video') return 'video';
    if (view === 'video' && !data.video) return 'lyrics';
    return view;
  }
  // How a video gets onto the panel. One decision, in one place:
  //   'sync'   YouTube and Bilibili: the panel plays the same video itself (muted) and follows the tab's
  //            position. The side screen then works by itself: the tab can be covered or minimised.
  //   'mirror' last resort, for sites without a player the panel can embed (or a video that refuses to
  //            be embedded): the extension copies frames from the tab, which needs its window visible.
  //   'none'   the source is gone: stop both, so nothing keeps playing or capturing unseen.
  // `syncFailed` = ids the embedded player refused (AnyVideo.failed).
  function syncKey(track) {
    const t = track || '', bili = /^bilibili:(BV[0-9A-Za-z]{10})(?::(\d+))?$/.exec(t);
    return /^youtube:([A-Za-z0-9_-]{11})$/.exec(t)?.[1] || (bili ? bili[1] + (bili[2] ? ':' + bili[2] : '') : null);
  }
  function videoPath(data = {}, syncFailed = new Set()) {
    if (!data.title || !data.video || !data.browser_bridge) return 'none';
    const id = syncKey(data.track);
    return id && !syncFailed.has(id) ? 'sync' : 'mirror';
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {resolve, follow, videoPath};
  else window.DeskMonMediaRoute = {resolve, follow, videoPath};
})();
