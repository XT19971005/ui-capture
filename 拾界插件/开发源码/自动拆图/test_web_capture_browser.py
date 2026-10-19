import json,threading,time,unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from server import app,TOKEN
from runtime import ROOT
class Fixture(BaseHTTPRequestHandler):
    image_url=None
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path=='/red.svg':
            self.send_response(200);self.send_header('Content-Type','image/svg+xml');self.end_headers();self.wfile.write(b'<svg xmlns="http://www.w3.org/2000/svg" width="240" height="120"><rect width="240" height="120" fill="#f36a22"/></svg>');return
        body='''<!doctype html><html><head><meta charset="utf-8"><title>网页抓取实测</title><style>body{margin:32px;background:#faf7ef;color:#23344a;font:20px Arial}button{background:#b19be8;border:0;border-radius:8px;padding:16px}.card{margin-top:20px;padding:20px;width:300px;border:1px solid #888}</style></head><body><h1>真实网页动态测试</h1><p id="live">初始内容</p><button>可以点击的按钮</button><div class="card">可编辑文字与形状</div><canvas id="canvas-scene" width="240" height="120"></canvas><script>const cc=document.getElementById("canvas-scene").getContext("2d");cc.fillStyle="#ed3762";cc.fillRect(0,0,240,120);setTimeout(()=>document.getElementById('live').textContent='动态内容已更新',300)</script></body></html>'''.encode('utf-8')
        if self.image_url:
            extra='<canvas id="tainted-scene" width="240" height="120"></canvas><script>const ci=new Image();ci.onload=()=>document.getElementById("tainted-scene").getContext("2d").drawImage(ci,0,0);ci.src="'+self.image_url+'";</script>'
            body=body.replace(b'</body>',extra.encode('utf-8')+b'</body>')
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(body)
class RealBrowserCapture(unittest.TestCase):
    def test_real_rendered_page_and_closed_target(self):
        cross=ThreadingHTTPServer(('127.0.0.1',0),Fixture);threading.Thread(target=cross.serve_forever,daemon=True).start();Fixture.image_url='http://127.0.0.1:'+str(cross.server_port)+'/red.svg'
        fixture=ThreadingHTTPServer(('127.0.0.1',0),Fixture);threading.Thread(target=fixture.serve_forever,daemon=True).start()
        bridge=app.extensions['shijie_web_capture'];bridge.headless=True;bridge.profile=ROOT/'依赖/运行临时/网页抓取验收浏览器'
        client=app.test_client();kwargs={'headers':{'X-Shijie-Token':TOKEN,'Origin':'http://127.0.0.1:19217'},'base_url':'http://127.0.0.1:19217'}
        try:
            r=client.post('/web/open',json={'url':'http://127.0.0.1:'+str(fixture.server_port)},**kwargs);self.assertEqual(r.status_code,200,r.get_json());target=r.get_json()['id'];time.sleep(.5)
            r=client.post('/web/capture',json={'target':target,'scope':'page'},**kwargs);self.assertEqual(r.status_code,200,r.get_json());data=r.get_json()['data'];text=json.dumps(data,ensure_ascii=False);self.assertIn('动态内容已更新',text);self.assertEqual(data['format'],'gugu-page-to-figma');self.assertGreater(data['count'],3)
            def collect(n):return [n]+[v for c in n.get('children',[]) for v in collect(c)]
            canvases=[n for n in collect(data['root']) if n.get('captureKind')=='canvas'];self.assertEqual(len(canvases),2);self.assertEqual(canvases[0]['type'],'image');self.assertTrue(canvases[0]['image'].startswith('data:image/png;base64,'));self.assertEqual(canvases[1]['captureProvenance'],'browser-raster');self.assertTrue(canvases[1]['rasterFallback'])
            import base64,io
            from PIL import Image
            pixel=Image.open(io.BytesIO(base64.b64decode(canvases[1]['image'].split(',')[1]))).convert('RGB').getpixel((120,60));self.assertEqual(pixel,(243,106,34))
            r=client.post('/web/capture',json={'target':target,'scope':'viewport'},**kwargs);self.assertEqual(r.status_code,200);self.assertEqual(r.get_json()['data']['scope'],'viewport')
            client.post('/web/close',json={'target':target},**kwargs);r=client.post('/web/capture',json={'target':target},**kwargs);self.assertEqual(r.status_code,502)
            out=ROOT.parent/'测试结果/拾界_网页抓取';out.mkdir(parents=True,exist_ok=True);(out/'真实浏览器抓取验收.json').write_text(json.dumps({'status':'PASS','canvasPixelsPreserved':True,'taintedCanvasActualScreenshotPixels':True,'dynamicRenderedContent':True,'fullPageAndViewport':True,'closedTargetRejected':True,'editableNodeCount':data['count']},ensure_ascii=False,indent=2),encoding='utf-8')
        finally:bridge.stop();fixture.shutdown();fixture.server_close();cross.shutdown();cross.server_close()
if __name__=='__main__':unittest.main()
