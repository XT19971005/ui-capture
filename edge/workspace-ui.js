/* Web-only distribution: open the local project library when requested. */
(()=>{const args=new URLSearchParams(location.search);if(args.has('library')){args.delete('library');history.replaceState(null,'',location.pathname+(args.size?'?'+args:''));window.addEventListener('load',()=>window.studio?.run('projects'),{once:true})}})();
