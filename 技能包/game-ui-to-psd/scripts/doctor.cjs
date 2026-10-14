const fs=require('fs'),cp=require('child_process'),{runtime}=require('./runtime.cjs');
const r=runtime(),checks=[];for(const key of ['node','python','agPsd','canvas','svgpath','psdTools','imagegenSkill','imagegenCLI'])checks.push({name:key,path:r[key],exists:!!r[key]&&fs.existsSync(r[key])});
for(const key of ['agPsd','canvas','svgpath']){try{require(r[key]);checks.push({name:key+' load',status:'PASS'});}catch(e){checks.push({name:key+' load',status:'FAIL',error:e.message});}}
const probe=cp.spawnSync(r.python,['-c','import sys;sys.path.insert(0,sys.argv[1]);import PIL,numpy,cv2,scipy,psd_tools;print("Python dependencies ready")',r.psdTools],{encoding:'utf8',windowsHide:true});
checks.push({name:'Python imports',status:probe.status===0?'PASS':'FAIL',detail:probe.error?.message||probe.stderr||probe.stdout});
const pass=checks.every(c=>c.exists!==false&&c.status!=='FAIL');console.log(JSON.stringify({status:pass?'PASS':'FAIL',checks,imagegen:{builtIn:'由 agent 检查当前会话是否提供 image_gen 工具；不是本地可执行文件',cli:'仅用户明确选择 CLI/API 后使用；此检查不会生成图片或发起付费请求'},visualReview:'本命令只验证运行环境，不能验收图片'},null,2));if(!pass)process.exitCode=1;
