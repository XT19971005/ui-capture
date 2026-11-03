'use strict';
(() => {
  const script = document.currentScript;
  window.SHIJIE = {prefix: script.dataset.prefix, user: Number(script.dataset.user), csrf: script.dataset.csrf};
  const headers = () => ({'Content-Type': 'application/json', 'X-CSRFToken': SHIJIE.csrf, 'X-Shijie-User': String(SHIJIE.user)});
  async function request(route, options = {}) {
    const response = await fetch(SHIJIE.prefix + '/api/' + route, {...options, headers: headers(), cache: 'no-store'});
    let data;
    try { data = await response.json(); } catch { throw Error('服务暂不可用，请重试'); }
    if (!response.ok) throw Error(data.error || '请求未完成');
    return data;
  }
  const exportFonts = new Map();
  const fontFiles = {'Noto Sans CJK SC': 'NotoSansCJKsc', 'Noto Serif CJK SC': 'NotoSerifCJKsc', 'Liberation Sans': 'LiberationSans', 'Liberation Serif': 'LiberationSerif'};
  async function portableArtwork(markup) {
    // ponytail: serializers put family/weight on each text tag; embed only the used deployed faces.
    const faces = new Map();
    for (const tag of markup.match(/<text\b[^>]*>/g) || []) for (const family of Object.keys(fontFiles)) {
      if (!tag.includes('font-family="' + family)) continue;
      const weight = Number(tag.match(/font-weight="([0-9]+)"/)?.[1] || 400) >= 600 ? 700 : 400;
      faces.set(family + ':' + weight, {family, weight});
    }
    if (!faces.size) return markup;
    const rules = await Promise.all([...faces].map(async ([key, {family, weight}]) => {
      if (!exportFonts.has(key)) exportFonts.set(key, (async () => {
        const face = weight === 700 ? 'Bold' : 'Regular';
        const response = await fetch(window.SHIJIE.prefix + '/static/server/fonts/' + fontFiles[family] + '-' + face + '.woff2');
        if (!response.ok) throw Error('导出字体加载失败，请刷新后重试');
        const blob = await response.blob();
        const signature = new Uint8Array(await blob.slice(0, 4).arrayBuffer());
        if (blob.size > 20 * 1024 * 1024 || signature.join(',') !== '119,79,70,50') throw Error('导出字体文件无效，请刷新后重试');
        return new Promise((resolve, reject) => {
          const reader = new FileReader(); reader.onload = () => resolve(reader.result);
          reader.onerror = () => reject(Error('导出字体读取失败，请重试')); reader.readAsDataURL(blob);
        });
      })().catch(error => { exportFonts.delete(key); throw error; }));
      return '@font-face{font-family:"' + family + '";font-style:normal;font-weight:' + weight + ';src:url(' + await exportFonts.get(key) + ') format("woff2")}';
    }));
    return markup.replace(/<svg\b[^>]*>/, opening => opening + '<style>' + rules.join('') + '</style>');
  }
  window.ShijieService = {headers, request, portableArtwork};
  window.addEventListener('load', async () => {
    // Load the same regular and bold faces used by Ubuntu before recalculating the workbench.
    if (document.fonts && window.studio) {
      try {
        await Promise.all(Object.keys(fontFiles).flatMap(family => [400, 700].map(weight => document.fonts.load(weight + ' 32px "' + family + '"'))));
        studio.sync(false);
      } catch {
        document.getElementById('status').textContent = '字体加载失败，文字外观可能不同；请刷新后导出。';
      }
    }
    const actions = document.querySelector('.header-actions');
    if (actions) {
      const tasks = document.createElement('a');
      tasks.href = SHIJIE.prefix + '/tasks/'; tasks.textContent = '任务记录'; actions.append(tasks);
      const logout = document.createElement('form');
      logout.method = 'post'; logout.action = SHIJIE.prefix + '/logout/';
      const csrf = document.createElement('input'); csrf.type = 'hidden'; csrf.name = 'csrfmiddlewaretoken'; csrf.value = SHIJIE.csrf;
      const button = document.createElement('button'); button.textContent = '退出登录';
      logout.append(csrf, button); actions.append(logout);
      try {
        const me = await request('me');
        if (me.admin) { const link = document.createElement('a'); link.href = SHIJIE.prefix + '/users/'; link.textContent = '账号授权'; actions.append(link); }
      } catch (e) { document.getElementById('status').textContent = e.message; }
    }
    const job = new URLSearchParams(location.search).get('job');
    if (job && window.studio) {
      try {
        const state = await request('engine/jobs/' + encodeURIComponent(job));
        const scene = state.result || state.partial || state.input;
        if (!scene) throw Error('任务暂未生成图层，请在任务记录中查看进度');
        if (scene.nodes?.some(node => node.generationRecord?.expandedCanvas)) await ShijieImageReplacement.growToFit(scene);
        await studio.adapter.load(scene);
        studio.setInitial(scene);
        studio.sync(true);
        const active = ['queued', 'running'].includes(state.status);
        document.getElementById('status').textContent = active
          ? '后台任务仍在运行：' + (state.message || '等待处理') + '。当前是已完成图层的快照；请在任务记录中打开完成结果。'
          : state.input ? '已找回任务原图，尚未产生拆分结果；重新拆分将发起新任务。' : '已找回任务图层，编辑后请保存工程。';
        if (active) {
          const start = document.getElementById('recognize');
          if (start) { start.textContent = '后台任务处理中'; start.disabled = true; }
          window.splitFeedback?.('running', '后台任务处理中：' + (state.message || '等待处理') + '。当前显示已完成图层的快照。');
          const badge = document.querySelector('.document-bar .doc-tag');
          if (badge) badge.textContent = '后台拆分中';
        }
      } catch (e) { document.getElementById('status').textContent = e.message; }
    }
  });
})();
