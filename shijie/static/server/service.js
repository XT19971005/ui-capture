'use strict';
(() => {
  const kind = document.querySelector('main').dataset.section, notice = document.getElementById('notice');
  const cell = (row, text) => { const td = document.createElement('td'); td.textContent = text; row.append(td); return td; };
  const states = {queued: '等待中', running: '处理中', completed: '处理结束', failed: '未完成', cancelled: '已取消'};
  async function refresh() {
    try {
      const users = kind === 'users', data = await ShijieService.request(users ? 'users' : 'engine/jobs');
      const head = document.querySelector('thead'), body = document.querySelector('tbody'); head.replaceChildren(); body.replaceChildren();
      const row = document.createElement('tr');
      for (const name of users ? ['账号', '当前权限', '授权'] : ['任务', '状态', '进度', '操作']) { const th = document.createElement('th'); th.textContent = name; row.append(th); } head.append(row);
      for (const item of users ? data.users : data.jobs) {
        const tr = document.createElement('tr');
        cell(tr, users ? item.email : item.title); cell(tr, users ? item.roles.join('、') || '待授权' : states[item.status] || item.status);
        if (!users) cell(tr, Math.round(item.progress * 100) + '% · ' + item.message);
        const actions = cell(tr, '');
        if (users && item.canManage) {
          const select = document.createElement('select'); select.setAttribute('aria-label', '设置 ' + item.email + ' 的权限');
          for (const role of ['', ...data.roles]) { const option = document.createElement('option'); option.value = role; option.textContent = role || '撤销权限'; option.selected = role === (item.roles[0] || ''); select.append(option); }
          const button = document.createElement('button'); button.textContent = '保存';
          button.onclick = async () => { try { await ShijieService.request('users', {method: 'POST', body: JSON.stringify({user: item.id, role: select.value || null})}); await refresh(); } catch (e) { notice.textContent = e.message; } };
          actions.append(select, button);
        } else if (!users) {
          const link = document.createElement('a'); link.textContent = '打开图层'; link.href = SHIJIE.prefix + '/image-editor.html?job=' + item.id; actions.append(link);
          if (['queued', 'running'].includes(item.status)) {
            const button = document.createElement('button'); button.textContent = '取消'; button.onclick = async () => { try { await ShijieService.request('engine/jobs/' + item.id, {method: 'DELETE'}); await refresh(); } catch (e) { notice.textContent = e.message; } }; actions.append(button);
          } else {
            const remove = document.createElement('button'); remove.textContent = '删除任务';
            remove.onclick = async () => {
              if (!confirm('删除此任务及其临时结果？已保存的工程会保留。')) return;
              try { await ShijieService.request('engine/jobs/' + item.id + '/purge', {method: 'POST'}); await refresh(); } catch (e) { notice.textContent = e.message; }
            }; actions.append(remove);
          }
        }
        body.append(tr);
      }
      notice.textContent = users ? '仅可调整权限范围内的账号。' : data.jobs.length ? '任务列表已更新。' : '暂无任务。';
    } catch (e) { notice.textContent = e.message; }
  }
  document.getElementById('refresh').onclick = refresh;
  refresh();
})();
