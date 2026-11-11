"""Read-only Codex readiness probe; no model turn is started."""
import json
from pathlib import Path
from codex_client import CLIENT

try:
    from desktop_connections import load_connections
    local=load_connections(Path(__file__).resolve().parents[1])
    if local and local[0].CONFIG.exists():
        state=local[0].status('tygpt');image=local[1].settings()
        if image['provider']=='aimake':
            from desktop_connections import credentials
            credentials(Path(__file__).resolve().parents[1],'tygpt',{'provider':image['provider'],'model':image['model']},'assistant-plan')
        print(json.dumps({**{k:state[k] for k in ('ready','models','model')},'imageGeneration':image['provider']=='aimake','analysisProvider':'tygpt','imageProvider':image['provider'],'imageModel':image['model']}))
        raise SystemExit(0)
    account=CLIENT.account()
    models=CLIENT.models() if account['ready'] else []
    ready=account['ready'] and account.get('provider')=='chatgpt' and bool(models)
    images=bool(CLIENT.call('modelProvider/capabilities/read',{}).get('imageGeneration')) if ready else False
    print(json.dumps({'ready':ready,'models':models if ready else [],'model':CLIENT.model() if ready else '', 'imageGeneration':images}))
finally:
    CLIENT.close()
