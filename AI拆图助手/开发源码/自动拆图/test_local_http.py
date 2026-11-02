import socket,unittest
from flask import Flask
from local_http import make_local_server

class ExclusiveServerTests(unittest.TestCase):
 def test_live_engine_port_cannot_be_reused(self):
  server=make_local_server(Flask('qa'),0)
  try:
   with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as second:
    second.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    with self.assertRaises(OSError):second.bind(('127.0.0.1',server.server_port))
  finally:server.server_close()
