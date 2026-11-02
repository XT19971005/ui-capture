"""Windows must not allow multiple engines to share the editor port."""
import os,socket
from werkzeug.serving import ThreadedWSGIServer

class ExclusiveLocalServer(ThreadedWSGIServer):
 allow_reuse_address=False
 def server_bind(self):
  if os.name=='nt':self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
  return super().server_bind()

def make_local_server(app,port=19217):return ExclusiveLocalServer('127.0.0.1',port,app)
