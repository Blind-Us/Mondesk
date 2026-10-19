"""Local printer preview and camera; credentials stay on the backend."""
import ftplib,io,json,re,socket,ssl,subprocess,threading,time,zipfile,tempfile
from urllib.parse import quote

class FTP(ftplib.FTP_TLS):
 def connect(self,host='',port=990,timeout=10):
  self.host=host;self.port=port;self.timeout=timeout
  self.sock=self.context.wrap_socket(socket.create_connection((host,port),timeout),server_hostname=host)
  self.af=self.sock.family;self.file=self.sock.makefile('r',encoding=self.encoding);self.welcome=self.getresp();return self.welcome
 def ntransfercmd(self,cmd,rest=None):
  conn,size=ftplib.FTP.ntransfercmd(self,cmd,rest)
  if self._prot_p:conn=self.context.wrap_socket(conn,server_hostname=self.host,session=self.sock.session)
  return conn,size

def preview(spec,report,on_objects=None):
 f=FTP(context=ssl._create_unverified_context(),encoding='utf-8')
 try:
  f.connect(spec['ip']);f.login('bblp',spec['access_code']);f.prot_p()
  name=report.get('subtask_name','');plate=re.search(r'plate_(\d+)',report.get('gcode_file',''))
  index=plate.group(1) if plate else '1'
  for path in [f'/Metadata/plate_{index}.png',f'/data/Metadata/plate_{index}.png']:
   out=io.BytesIO()
   try:f.retrbinary('RETR '+path,out.write);data=out.getvalue()
   except ftplib.all_errors:continue
   if data.startswith(b'\x89PNG'):return data
  files=f.nlst('/')+f.nlst('/cache')
  normalize=lambda value:re.sub(r'[\s_]+','',value).casefold()
  wanted=[normalize(name+'.gcode.3mf'),normalize(name+'.3mf')]
  files=[x for x in files if x.lower().endswith('.3mf') and normalize(x.rsplit('/',1)[-1]) in wanted]
  for path in files[:1]:
   out=io.BytesIO()
   def write(chunk):
    if out.tell()+len(chunk)>100*1024*1024:raise ValueError('preview archive too large')
    out.write(chunk)
   f.retrbinary('RETR '+path,write)
   with zipfile.ZipFile(out) as z:
    if on_objects and 'Metadata/slice_info.config' in z.namelist():
     import xml.etree.ElementTree as ET
     if z.getinfo('Metadata/slice_info.config').file_size>4*1024*1024:raise ValueError('metadata too large')
     root=ET.fromstring(z.read('Metadata/slice_info.config'))
     for plate in root.findall('plate'):
      meta={m.get('key'):m.get('value') for m in plate.findall('metadata')}
      if meta.get('index')==index:
       objects=[{'id':int(o.get('identify_id')),'name':o.get('name') or '物件','skipped':o.get('skipped')=='true'} for o in plate.findall('object') if (o.get('identify_id') or '').isdigit()]
       on_objects(objects,meta.get('label_object_enabled')=='true')
    paths=[f'Metadata/plate_{index}.png',f'Metadata/plate_{index}_small.png','Metadata/plate_1.png','Metadata/thumbnail.png']
    for image in paths:
     if image in z.namelist() and z.getinfo(image).file_size<10*1024*1024:return z.read(image)
 finally:f.close()

def studio_stream():
 """The local RTP stream from Bambu Studio's camera tool, if it is running."""
 import os,sys
 base=os.path.join(os.environ.get('APPDATA',''),'BambuStudio') if sys.platform=='win32' else os.path.expanduser('~/.config/BambuStudio')
 sdp=os.path.join(base,'cameratools','ffmpeg.sdp')
 if not os.path.isfile(sdp):return None
 try:
  if sys.platform=='win32':
   out=subprocess.run(['tasklist','/FI','IMAGENAME eq bambu_source.exe','/NH'],capture_output=True,text=True,timeout=5,creationflags=0x08000000).stdout
   running='bambu_source.exe' in out.lower()
  else:
   running=subprocess.run(['pgrep','-f','bambu_source'],capture_output=True,timeout=5).returncode==0
 except Exception:running=False
 return sdp if running else None

def studio_port(sdp):
 """RTP port from Studio's SDP file (m=video <port> ...), default 1234."""
 try:
  m=re.search(r'^m=video\s+(\d+)',open(sdp,encoding='utf-8').read(),re.M)
  return int(m.group(1)) if m else 1234
 except OSError:return 1234

def rtp_to_h264(port,proc):
 """Receive H.264 RTP (RFC 6184) on localhost and write Annex-B NAL units to ffmpeg's stdin."""
 import struct
 s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
 s.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,8<<20)
 try:
  s.bind(('127.0.0.1',port));s.settimeout(1)
  start=b'\x00\x00\x00\x01'
  while proc.poll() is None:
   try:p=s.recv(65536)
   except socket.timeout:continue
   if len(p)<13:continue
   payload=p[12+4*(p[0]&0x0f):];kind=payload[0]&0x1f
   if kind<24:out=start+payload                       # single NAL unit
   elif kind==24:                                     # STAP-A: several NAL units
    out=b'';i=1
    while i+2<=len(payload):
     n=struct.unpack('!H',payload[i:i+2])[0];i+=2;out+=start+payload[i:i+n];i+=n
   elif kind==28:                                     # FU-A: fragment of one NAL unit
    fu=payload[1]
    out=(start+bytes([(payload[0]&0xe0)|(fu&0x1f)]) if fu&0x80 else b'')+payload[2:]
   else:continue
   try:proc.stdin.write(out)
   except (BrokenPipeError,OSError,ValueError):break
 finally:s.close()

class Camera:
 def __init__(self,spec):self.spec=spec;self.frame=None;self.sampled=0;self.error='';self.process=None;self.lock=threading.Lock();self.last_request=0;self.retry_after=0
 def start(self,report):
  self.last_request=time.time()
  with self.lock:
   if getattr(self,'worker',None) and self.worker.is_alive():return
   if time.time()<self.retry_after:return
   self.error='正在連接攝影機…';self.frame=None
   self.worker=threading.Thread(target=self.run,args=(report,),daemon=True);self.worker.start()
 def run(self,report):
  errors=None
  try:
   from imageio_ffmpeg import get_ffmpeg_exe
   errors=tempfile.TemporaryFile()
   studio=studio_stream()
   rtp_port=None
   if studio and self.spec.get('camera_source','auto')!='lan':
    # Bambu Studio's camera tool (bambu_source + ffmpeg) relays the camera to local RTP
    # through Bambu's own channel: works in cloud mode, no LAN Liveview needed. Its RTP
    # gives every frame the same timestamp, which makes ffmpeg's RTP reader merge frames,
    # so we unpack the RTP ourselves and feed raw H.264 (timed by arrival) to ffmpeg.
    rtp_port=studio_port(studio)
    source=['-use_wallclock_as_timestamps','1','-f','h264','-i','pipe:0'];vf='fps=10,scale=960:-2'
   else:
    vf='fps=4,scale=960:-2'
    raw=(report.get('ipcam') or {}).get('rtsp_url','')
    if raw=='disable':self.error='請在印表機設定開啟 LAN Only Liveview，或在 Bambu Studio 開啟攝影機直播工具';return
    ip=self.spec['ip'];code=quote(self.spec['access_code'],safe='')
    source=['-rtsp_transport','tcp','-timeout','8000000','-i',f'rtsps://bblp:{code}@{ip}:322/streaming/live/1']
   self.process=subprocess.Popen([get_ffmpeg_exe(),'-loglevel','error',*source,'-an','-vf',vf,'-f','image2pipe','-vcodec','mjpeg','-q:v','5','-flush_packets','1','pipe:1'],stdin=subprocess.PIPE if rtp_port else None,stdout=subprocess.PIPE,stderr=errors,bufsize=0,creationflags=0x08000000 if __import__('sys').platform=='win32' else 0)
   if rtp_port:threading.Thread(target=rtp_to_h264,args=(rtp_port,self.process),daemon=True).start()
   # read() below blocks while ffmpeg has no output; this watchdog ends ffmpeg once nobody
   # is watching (or nothing arrives), so a silent stream can't hold the port forever.
   proc=self.process
   def watchdog():
    while proc.poll() is None:
     idle=time.time()-self.last_request>20
     silent=time.time()-max(self.sampled,started)>45
     if idle or silent:
      proc.kill();return
     time.sleep(1)
   started=time.time()
   threading.Thread(target=watchdog,daemon=True).start()
   buf=b''
   while time.time()-self.last_request<20:
    chunk=self.process.stdout.read(4096)
    if not chunk:break
    buf+=chunk
    while b'\xff\xd9' in buf:
     end=buf.index(b'\xff\xd9')+2;part,buf=buf[:end],buf[end:];start=part.find(b'\xff\xd8')
     if start>=0:self.frame=part[start:];self.sampled=time.time();self.error=''
    if len(buf)>8*1024*1024:buf=b''
   if not self.frame:
    self.stop();errors.seek(0);detail=errors.read(32000).decode('utf-8','replace').lower()
    if '401' in detail or 'unauthorized' in detail:self.error='攝影機拒絕登入，請確認 LAN 存取碼與直播權限'
    elif 'tls' in detail:self.error='攝影機 TLS 連線中斷，未收到影像；請確認印表機已開啟 LAN Only Liveview'
    else:self.error='攝影機未提供影像串流：請在 Bambu Studio 開啟攝影機直播工具，或在印表機開啟 LAN Only Liveview'
  except ImportError:self.error='缺少直播解碼套件 imageio-ffmpeg，請更新專案依賴套件'
  except Exception:self.error='攝影機暫時無法連線'
  finally:
   self.stop()
   if errors:errors.close()
   if self.error:self.retry_after=time.time()+15
 def stop(self):
  p=self.process
  if p and p.poll() is None:
   p.terminate()
   try:p.wait(timeout=2)
   except subprocess.TimeoutExpired:p.kill()
