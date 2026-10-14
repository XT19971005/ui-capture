#target photoshop
(function(){
var base="D:/@谢涛/@TUSY/麻将/2026_8_24AI/2026_10_9UI拆分/拾界插件/自检记录/Photoshop验收/";
function report(s){var f=new File(base+"文字编辑验收.txt");f.encoding="UTF8";f.open("w");f.write(s);f.close();}
var previous=app.documents.length?app.activeDocument:null,oldDialogs=app.displayDialogs,doc=null;
try{
 report("STARTED");app.displayDialogs=DialogModes.NO;
 doc=app.open(new File("D:/@谢涛/@TUSY/麻将/2026_8_24AI/2026_10_9UI拆分/拾界插件/自检记录/自检/native-fixture.psd"));var texts=[],shapes=0;
 function visit(parent){for(var i=0;i<parent.layers.length;i++){var l=parent.layers[i];if(l.typename==="LayerSet")visit(l);else if(l.kind===LayerKind.TEXT)texts.push(l);else if(l.kind===LayerKind.SOLIDFILL)shapes++;}}
 visit(doc);if(texts.length<4||shapes<8)throw Error("Native layer types missing: "+texts.length+"/"+shapes);
 if(doc.layers[doc.layers.length-1].name!=="页面背景")throw Error("Background not at bottom");
 var target=null;for(var i=0;i<texts.length;i++)if(texts[i].textItem.contents==="文字可以编辑")target=texts[i];
 if(!target)throw Error("Title text not found");target.textItem.contents="文字编辑成功";
 doc.saveAs(new File(base+"文字编辑验收.psd"),new PhotoshopSaveOptions(),true,Extension.LOWERCASE);
 doc.saveAs(new File(base+"文字编辑验收.png"),new PNGSaveOptions(),true,Extension.LOWERCASE);
 doc.close(SaveOptions.DONOTSAVECHANGES);doc=null;
 doc=app.open(new File(base+"文字编辑验收.psd"));texts=[];shapes=0;visit(doc);var found=false;for(var i=0;i<texts.length;i++)if(texts[i].textItem.contents==="文字编辑成功")found=true;
 if(!found)throw Error("Edited text lost after reopen");
 report("PASS\nPhotoshop "+app.version+"\nNative text layers: "+texts.length+"\nNative vector shapes: "+shapes+"\nText edited, saved and reopened successfully.\nBackground at bottom.");
}catch(e){report("FAIL\n"+e.message+"\nLine: "+e.line);}
finally{if(doc)doc.close(SaveOptions.DONOTSAVECHANGES);app.displayDialogs=oldDialogs;if(previous)app.activeDocument=previous;}
})();

