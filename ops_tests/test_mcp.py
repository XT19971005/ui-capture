import os,unittest
"""Official MCP client over real HTTP and a private Unix executor."""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import socket
import threading
import time
import unittest
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
import uvicorn
from . import test_release as fixtures
from shijie_ops.runtime import Operations, Server, Handler


@asynccontextmanager
async def connection(url, token):
    async with httpx.AsyncClient(headers={'Authorization':'Bearer '+token}) as client:
        async with streamable_http_client(url,http_client=client) as streams:
            yield streams


@unittest.skipIf(os.name=='nt', 'Linux deployment lifecycle requires Linux host')
class MCPTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from shijie_ops.mcp import create_app
        asyncio.get_running_loop().slow_callback_duration=5
        self.host=fixtures.ReleaseTest(); self.host.setUp(); self.addCleanup(self.host.doCleanups)
        self.identities=self.host.root/'identities.json'
        self.identities.write_text(json.dumps({'admin@example.invalid':True,'reader@example.invalid':True}))
        self.ops=Operations(self.host.config,self.host.root/'ops',env={**self.host.env,'IDENTITIES':str(self.identities)})
        self.addCleanup(self.ops.close)
        self.sock=self.host.root/'control.sock'; self.backend=Server(str(self.sock),Handler); self.backend.operations=self.ops
        self.thread=threading.Thread(target=self.backend.serve_forever,daemon=True); self.thread.start()
        self.token='synthetic-test-token-'+'a'*40; self.read_token='synthetic-reader-'+'b'*40
        self.operators=self.host.root/'operators.json'
        self.operators.write_text(json.dumps({actor:{'sha256':hashlib.sha256(token.encode()).hexdigest(),'role':role}
          for actor,token,role in [('admin@example.invalid',self.token,'deploy'),('reader@example.invalid',self.read_token,'read')]}))
        self.operators.chmod(0o600)
        with socket.socket() as reservation: reservation.bind(('127.0.0.1',0)); port=reservation.getsockname()[1]
        self.url=f'http://127.0.0.1:{port}/mcp'
        self.server=uvicorn.Server(uvicorn.Config(create_app(self.operators,self.sock),host='127.0.0.1',port=port,log_level='error'))
        self.http_thread=threading.Thread(target=self.server.run,daemon=True); self.http_thread.start()
        deadline=time.monotonic()+5
        while not self.server.started:
            self.assertLess(time.monotonic(),deadline); await asyncio.sleep(.02)

    async def asyncTearDown(self):
        self.server.should_exit=True; await asyncio.to_thread(self.http_thread.join,5)
        await asyncio.to_thread(self.backend.shutdown); self.backend.server_close(); self.thread.join(5)

    async def test_official_discovery_diagnostics_and_immediate_revocation(self):
        async with httpx.AsyncClient() as http:
            self.assertEqual((await http.post(self.url,json={})).status_code,401)
        async with connection(self.url,self.token) as (read,write,_):
            async with ClientSession(read,write) as session:
                initialized=await session.initialize(); self.assertEqual(initialized.serverInfo.name,'Shijie Operations')
                names={tool.name for tool in (await session.list_tools()).tools}
                self.assertEqual(names,{'get_project_status','diagnose','get_logs','get_job','deploy','resume_deployment','repair_deployment','control_service','backup'})
                result=await session.call_tool('diagnose',{}); self.assertFalse(result.isError,result)
                self.assertEqual(result.structuredContent['project'],'shijie')
        self.identities.write_text('{}')
        async with httpx.AsyncClient(headers={'Authorization':'Bearer '+self.token}) as http:
            self.assertEqual((await http.post(self.url,json={})).status_code,403)

    async def test_read_only_token_cannot_write_or_view_secrets(self):
        async with connection(self.url,self.read_token) as (read,write,_):
            async with ClientSession(read,write) as session:
                await session.initialize()
                denied=await session.call_tool('control_service',{'operation':'restart','service':'web','request_id':'reader'})
                self.assertTrue(denied.isError); self.assertIsNone(self.ops.snapshot()['latest_job'])
                result=await session.call_tool('get_logs',{'service':'web'})
                self.assertFalse(result.isError); self.assertNotIn('hidden-synthetic-token',result.structuredContent['text'])

    async def test_real_http_async_release_and_retry(self):
        commit=self.host.commit('http-release'); params={'commit':commit,'request_id':'http-one'}
        async with connection(self.url,self.token) as (read,write,_):
            async with ClientSession(read,write) as session:
                await session.initialize(); result=await session.call_tool('deploy',params)
                self.assertFalse(result.isError,result); job=result.structuredContent
        async with connection(self.url,self.token) as (read,write,_):
            async with ClientSession(read,write) as session:
                await session.initialize(); retry=await session.call_tool('deploy',params)
                self.assertEqual(retry.structuredContent['id'],job['id'])
                for _ in range(400):
                    row=(await session.call_tool('get_job',{'job_id':job['id']})).structuredContent
                    if row['status'] not in ('queued','running'):break
                    await asyncio.sleep(.025)
                self.assertEqual(row['status'],'succeeded',row)

    async def test_ip_gateway_discovery_identity_spoofing_and_outage(self):
        from shijie_ops.mcp import create_app
        app=create_app(self.operators,self.sock, trusted_client_ips=['10.103.38.87'],trust_loopback_proxy=True)
        headers={'X-Forwarded-For':'10.103.38.87','Content-Type':'application/json','Accept':'application/json, text/event-stream'}
        async with app.app.app.router.lifespan_context(app.app.app):
            transport=httpx.ASGITransport(app=app,client=('127.0.0.1',10000))
            async with httpx.AsyncClient(transport=transport,base_url='http://localhost:8095',headers=headers) as http:
                discovered=await http.post('/mcp',json={'jsonrpc':'2.0','id':1,'method':'tools/list'})
                self.assertEqual(discovered.status_code,200)
                call={'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'get_project_status','arguments':{}}}
                self.assertEqual((await http.post('/mcp',json=call)).status_code,401)
                identity={'X-User-Email':'admin@example.invalid','X-User-Name':'Admin'}
                self.assertEqual((await http.post('/mcp',json=call,headers=identity)).status_code,200)
                self.assertEqual((await http.post('/mcp',json=call,headers={'X-User-Email':'admin@example.invalid'})).status_code,401)
                self.assertEqual((await http.post('/mcp',json=call,headers={**identity,'X-User-Name':'bad%0Aname'})).status_code,400)
                self.assertEqual((await http.post('/mcp',json=call,headers=[('X-User-Email','admin@example.invalid'),('X-User-Email','other@example.invalid'),('X-User-Name','Admin')])).status_code,400)
                self.assertEqual((await http.post('/mcp',json=call,headers={**identity,'Origin':'https://untrusted.example.invalid'})).status_code,403)
                self.identities.write_text('{}')
                self.assertEqual((await http.post('/mcp',json=call,headers=identity)).status_code,403)
                self.identities.write_text('{"admin@example.invalid":true}')
                self.sock.rename(self.sock.with_suffix('.offline'))
                try:
                    self.assertEqual((await http.post('/mcp',json=call,headers=identity)).status_code,503)
                    self.assertEqual((await http.post('/mcp',json={'jsonrpc':'2.0','id':3,'method':'tools/list'})).status_code,200)
                finally:self.sock.with_suffix('.offline').rename(self.sock)
                self.assertEqual((await http.post('/mcp',content=b'x'*65537)).status_code,413)
            for peer,forwarded in [('10.103.38.88','10.103.38.87'),('127.0.0.1','10.103.38.87, 10.103.38.88'),('127.0.0.1','')]:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=(peer,10000)),headers={**headers,'X-Forwarded-For':forwarded}) as http:
                    self.assertEqual((await http.post('http://localhost:8095/mcp',json={})).status_code,403)
