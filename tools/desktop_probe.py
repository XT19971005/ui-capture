"""Read-only Codex readiness probe; no model turn is started."""
import json
from codex_client import CLIENT

try:
    account=CLIENT.account()
    models=CLIENT.models() if account['ready'] else []
    ready=account['ready'] and account.get('provider')=='chatgpt' and bool(models)
    images=bool(CLIENT.call('modelProvider/capabilities/read',{}).get('imageGeneration')) if ready else False
    print(json.dumps({'ready':ready,'models':models if ready else [],'model':CLIENT.model() if ready else '', 'imageGeneration':images}))
finally:
    CLIENT.close()
