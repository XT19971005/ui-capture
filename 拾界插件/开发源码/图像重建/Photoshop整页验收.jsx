#target photoshop
(function(){
var base="D:/@谢涛/@TUSY/麻将/2026_8_24AI/2026_10_9UI拆分/拾界插件/自检记录/Photoshop验收/",prev=app.documents.length?app.activeDocument:null,dialog=app.displayDialogs,doc;
function report(s){var f=new File(base+"最终验证结果.txt");f.encoding="UTF8";f.open("w");f.write(s);f.close();}
try{report("STARTED");app.displayDialogs=DialogModes.NO;doc=app.open(new File("D:/@谢涛/@TUSY/麻将/2026_8_24AI/2026_10_9UI拆分/拾界插件/插件程序/示例/专注App_可编辑分层.psd"));var texts=0,shapes=0,issues=[];
function visit(group){for(var i=0;i<group.layers.length;i++){var l=group.layers[i];if(l.typename==="LayerSet")visit(l);else if(l.kind===LayerKind.TEXT){var t=l.textItem.contents;try{l.textItem.contents=t;texts++;}catch(textError){issues.push(l.name+" | "+t+" | "+textError.message);}}else if(l.kind===LayerKind.SOLIDFILL)shapes++;}}visit(doc);
doc.saveAs(new File(base+"专注页面_Photoshop实际重排.png"),new PNGSaveOptions(),true,Extension.LOWERCASE);
if(issues.length)throw Error(issues.join("\n"));if(texts!==61||shapes!==53)throw Error("Unexpected types "+texts+"/"+shapes);
report("PASS\nPhotoshop "+app.version+"\n61 text layers regenerated using Photoshop text engine.\n53 native shape layers.\nRoot bottom: "+doc.layers[doc.layers.length-1].name);
}catch(e){report("FAIL\n"+e.message+"\nLine "+e.line);}
finally{if(doc)doc.close(SaveOptions.DONOTSAVECHANGES);app.displayDialogs=dialog;if(prev)app.activeDocument=prev;}
})();

