// Record actual image review separately from structural checks. Never auto-mark images PASS.
const fs=require('fs'),path=require('path'),{sha}=require('./complete_assets.cjs');
const command=process.argv[2],p=process.argv.indexOf('--project'),root=path.resolve(process.argv[p+1]||''),dirs=require('./project_dirs.cjs')(root);
if(p<0||!['init','check'].includes(command))throw Error('review.cjs init|check --project DIR');
const job=JSON.parse(fs.readFileSync(path.join(root,(dirs.plan+'/项目.json')),'utf8')),qa=path.join(root,(dirs.qa)),file=path.join(qa,'画面复核.json'),psd=path.join(root,(dirs.output),job.outputName||'可编辑分层.psd');
const psdHash=sha(psd),leaves=items=>items.flatMap(s=>s.kind==='group'?leaves(s.children):[s]);
if(command==='init'){
 if(fs.existsSync(file)&&JSON.parse(fs.readFileSync(file,'utf8')).psdSHA256===psdHash){console.log('Existing review checklist matches PSD; preserving actual review records.');process.exit(0);}
 const candidates=[['原图与整体合成',(dirs.qa+'/原图与合成_并排检查.png')],['完整人物浅色底',(dirs.qa+'/角色透明检查_浅色.png')],['完整人物深色底',(dirs.qa+'/角色透明检查_深色.png')],['完整人物棋盘格',(dirs.qa+'/角色透明检查_棋盘格.png')],['完整背景',((dirs.compact?dirs.qa:dirs.output)+'/完整背景.png')]];
 for(const [index,s] of leaves(job.layers).entries())candidates.push([s.name,(dirs.qa+'/独立图层/')+String(index+1).padStart(3,'0')+'_'+s.name.replace(/[\\/:*?"<>|]/g,'_')+'.png']);
 const checks=candidates.filter(([,f])=>fs.existsSync(path.join(root,f))).map(([name,f])=>({name,file:f,sha256:sha(path.join(root,f)),status:'PENDING',notes:''}));
 fs.writeFileSync(file,JSON.stringify({psdSHA256:psdHash,instruction:'agent 实际查看每张图后记录观察及 PASS/FAIL，不得由脚本自动填写；有问题先修图再复核。',checks,issues:[]},null,2));console.log(JSON.stringify({stage:'VISUAL_REVIEW',status:'REQUIRED',file,count:checks.length}));
}else{
 if(!fs.existsSync(file))throw Error('没有实际画面复核记录，先运行 review init 并查看图像');
 const report=JSON.parse(fs.readFileSync(file,'utf8')),audit=JSON.parse(fs.readFileSync(path.join(qa,'检查结果.json'),'utf8')),state=JSON.parse(fs.readFileSync(path.join(qa,'流水线状态.json'),'utf8'));
 const errors=[];if(report.psdSHA256!==psdHash||state.verify?.psdSHA256!==psdHash)errors.push('PSD 已变更，必须重跑回读和实际画面检查');
 if(audit.psdSHA256!==psdHash||audit.projectManifestSHA256!==sha(path.join(root,(dirs.plan+'/项目.json'))))errors.push('回读报告不对应当前项目或 PSD');
 for(const [input,hash] of Object.entries(audit.verifiedInputs||{})){const f=path.isAbsolute(input)?input:path.resolve(root,input);if(!fs.existsSync(f)||sha(f)!==hash)errors.push('回读后输入素材已改写: '+input);}
 if(audit.structuralChecks!=='PASS'||audit.assetChecks!=='PASS')errors.push('结构或素材检查尚未通过');
 if(!report.checks.length)errors.push('缺少画面检查项目');
 for(const c of report.checks){if(c.status!=='PASS'||!c.notes.trim())errors.push('未实际确认: '+c.name);if(!fs.existsSync(path.join(root,c.file))||sha(path.join(root,c.file))!==c.sha256)errors.push('检查图片已变更: '+c.name);}
 if(report.issues?.length)errors.push('存在未解决画面问题');
 if(errors.length){console.log(JSON.stringify({status:'FAIL',errors},null,2));process.exitCode=1;}else{state.visualReview='PASS';state.visualReviewRecord={psdSHA256:psdHash,file:(dirs.qa+'/画面复核.json'),completedAt:new Date().toISOString()};fs.writeFileSync(path.join(qa,'流水线状态.json'),JSON.stringify(state,null,2));console.log(JSON.stringify({status:'PASS',note:'仅验证复核记录与当前文件一致，记录必须来自实际看图；不代替 Photoshop 编辑测试。'}));}
}
