/* Shared Codex supplies computation; each browser owns its project files. */
'use strict';
(() => {
  if (!window.SHIJIE?.sharedCodex) return;
  const owner = String(SHIJIE.user), store = 'directories', extension = '.aisplit-project', legacyExtension = '.shijie-project';
  // One origin-wide lock also covers two accounts explicitly choosing the same folder.
  const lockName = 'shijie-browser-project-files-v1', headerLimit = 65536, fileLimit = 276 * 1024 * 1024;
  let database, selection = null;
  const unsupported = '当前使用手动文件模式：点击“导出工程”下载到自己电脑，下次用“导入外部工程”打开。生成结果仅在本页保留，刷新或关闭前请完成下载。HTTPS 下的新版 Chrome / Edge 可连接本机文件夹。';
  const conflict = () => Error('工程已在另一个页面更新或删除；当前修改仍在页面中，请重新打开或导出工程副本。');
  const directoryChanged = () => Error('工程目录已切换，请刷新列表并确认保存位置；当前修改仍在页面中。');
  function supported() {
    return window.isSecureContext === true && typeof window.showDirectoryPicker === 'function' &&
      !!window.indexedDB && typeof navigator.locks?.request === 'function' &&
      typeof CompressionStream === 'function' && typeof DecompressionStream === 'function';
  }
  function available() {
    if (!SHIJIE.sharedCodex || String(SHIJIE.user) !== owner) throw Error('登录账号已改变，请刷新页面后连接自己的工程目录。');
    if (!supported()) throw Error(unsupported);
  }
  function db() {
    if (!database) database = new Promise((resolve, reject) => {
      const request = indexedDB.open('shijie-local-directory-handles', 1);
      request.onupgradeneeded = () => { if (!request.result.objectStoreNames.contains(store)) request.result.createObjectStore(store); };
      request.onsuccess = () => { request.result.onversionchange = () => { request.result.close(); database = null; }; resolve(request.result); };
      request.onerror = () => reject(Error('无法读取本地目录授权设置，请检查浏览器权限；工程不会改存服务器。'));
      request.onblocked = () => reject(Error('本地目录设置正在被其他页面使用，请关闭旧页面后重试。'));
    }).catch(error => { database = null; throw error; });
    return database;
  }
  async function setting(value) {
    const connection = await db();
    return new Promise((resolve, reject) => {
      const tx = connection.transaction(store, value === undefined ? 'readonly' : 'readwrite');
      const request = value === undefined ? tx.objectStore(store).get(owner) : tx.objectStore(store).put(value, owner);
      let result;
      request.onsuccess = () => { result = request.result; };
      tx.oncomplete = () => resolve(value === undefined ? result || null : value);
      tx.onerror = tx.onabort = () => reject(Error('本地目录设置保存或读取失败，请重试；原工程与当前编辑保留。'));
    });
  }
  async function permission(handle) {
    if (!handle || handle.kind !== 'directory') throw Error('请先在“打开工程”中选择自己电脑上的工程文件夹。');
    let state = await handle.queryPermission({mode: 'readwrite'});
    // Renew only from an explicit user gesture; refresh and progress stay quiet.
    if (state === 'prompt' && navigator.userActivation?.isActive && typeof handle.requestPermission === 'function') {
      try { state = await handle.requestPermission({mode: 'readwrite'}); } catch {}
    }
    if (state !== 'granted')
      throw Error('本地文件夹的读写权限已失效，请点击“选择本地文件夹”重新授权；当前编辑保留。');
  }
  async function current(expected, required = true) {
    available();
    const value = await setting();
    if (expected && value?.id !== expected) throw directoryChanged();
    selection = value;
    if (!value) {
      if (required) throw Error('请先在“打开工程”中选择自己电脑上的工程文件夹；也可导出工程文件。');
      return null;
    }
    await permission(value.handle);
    return value;
  }
  function pickDirectory() {
    // Must run directly in the click stack, before queues, IDB or other awaits.
    try { available(); return window.showDirectoryPicker({id: 'shijie-projects', mode: 'readwrite'}); }
    catch (error) { return Promise.reject(error); }
  }
  async function setDirectory(handle) {
    available();
    return navigator.locks.request(lockName, async () => {
      await permission(handle);
      const previous = await setting();
      const same = previous && await handle.isSameEntry(previous.handle);
      const next = {id: same ? previous.id : 'browser-folder:' + crypto.randomUUID(), handle};
      // Only an opaque identifier and directory handle enter IndexedDB, never project bodies.
      await setting(next);
      selection = next;
      return {directory: next.id, directoryName: handle.name};
    });
  }
  function validId(id) {
    if (typeof id !== 'string' || !/^[A-Za-z0-9_-]{1,160}$/.test(id)) throw Error('工程标识无效。');
  }
  async function readHeader(file) {
    const prefix = new Uint8Array(await file.slice(0, headerLimit + 1).arrayBuffer()), newline = prefix.indexOf(10);
    if (newline < 0 || newline >= headerLimit) throw Error('本地工程索引损坏，原文件已保留。');
    const meta = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(prefix.subarray(0, newline)));
    if (meta?.storageVersion !== 'local-disk-v1' || !Number.isSafeInteger(meta.updated) ||
        typeof meta.title !== 'string' || typeof meta.persistedVersion !== 'string' || !meta.persistedVersion || meta.persistedVersion.length > 160)
      throw Error('本地工程索引或版本无效，原文件已保留。');
    validId(meta.id);
    return {meta, offset: newline + 1};
  }
  async function entries(handle) {
    const projects = new Map(), names = new Set();
    let unreadable = 0;
    for await (const [name, fileHandle] of handle.entries()) {
      names.add(name.toLocaleLowerCase());
      if (fileHandle.kind !== 'file' || ![extension, legacyExtension].some(suffix => name.toLocaleLowerCase().endsWith(suffix))) continue;
      try {
        const {meta} = await readHeader(await fileHandle.getFile()), old = projects.get(meta.id);
        if (!old || meta.updated > old.meta.updated || meta.updated === old.meta.updated && name > old.name)
          projects.set(meta.id, {name, handle: fileHandle, meta});
      } catch (error) {
        if (error.name === 'NotAllowedError' || error.name === 'SecurityError') throw error;
        unreadable++;
      }
    }
    return {projects, names, unreadable};
  }
  async function readProject(file, ident) {
    if (file.size > fileLimit + headerLimit) throw Error('工程文件超过容量限制。');
    const {meta, offset} = await readHeader(file);
    if (meta.id !== ident) throw Error('工程索引不匹配。');
    const reader = file.slice(offset).stream().pipeThrough(new DecompressionStream('gzip')).getReader();
    const decoder = new TextDecoder('utf-8', {fatal: true});
    let total = 0, text = '';
    try {
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        total += chunk.value.byteLength;
        if (total > fileLimit) throw Error('工程文件超过容量限制。');
        text += decoder.decode(chunk.value, {stream: true});
      }
      text += decoder.decode();
    } catch (error) {
      await reader.cancel().catch(() => {});
      throw Error('本地工程压缩内容损坏或超过容量限制，原文件已保留。');
    }
    const wire = JSON.parse(text);
    if (wire?.wireFormat !== 'shijie-image-table' || wire.wireVersion !== 1) throw Error('本地工程格式无效。');
    const record = ShijieProjectCodec.decode({format: 'shijie-project', version: 1, doc: wire.job, images: wire.images});
    if (record.id !== ident || record.persistedVersion !== meta.persistedVersion || !record.doc || record.doc._projectId !== ident)
      throw Error('本地工程内容与索引不匹配，原文件已保留。');
    return record;
  }
  function unpack(value) {
    if (value?.wireFormat === 'shijie-image-table' && value.wireVersion === 1)
      return ShijieProjectCodec.decode({format: 'shijie-project', version: 1, doc: value.job, images: value.images});
    return value;
  }
  function filename(title, names, previous, renameLegacy = false) {
    // Ordinary saves keep legacy paths. Only a user or AI title change migrates that one file.
    if (previous?.name.toLocaleLowerCase().endsWith(legacyExtension) && !renameLegacy) return previous.name;
    let base = title.replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').replace(/^[ .]+|[ .]+$/g, '').slice(0, 80).replace(/[ .]+$/g, '') || '未命名工程';
    if (/^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])$/i.test(base.split('.')[0].trim())) base = '工程_' + base;
    for (let i = 1; ; i++) {
      const name = base + (i === 1 ? '' : '（' + i + '）') + extension;
      if (previous?.name.toLocaleLowerCase() === name.toLocaleLowerCase()) return previous.name;
      if (!names.has(name.toLocaleLowerCase())) return name;
    }
  }
  function checkVersion(entry, expected) {
    if ((entry?.meta.persistedVersion || null) !== (expected ?? null)) throw conflict();
  }
  async function save(folder, ident, record) {
    if (!record || record.id !== ident || record.saveMode !== 'saved' || !['image', 'web'].includes(record.kind) ||
        !record.doc || record.doc._projectId !== ident || typeof record.title !== 'string' || record.title.length > 1000)
      throw Error('保存工程参数无效。');
    const listing = await entries(folder.handle), previous = listing.projects.get(ident);
    checkVersion(previous, record._expectedVersion);
    const now = Math.max(Date.now(), (previous?.meta.updated || 0) + 1);
    const meta = {id: ident, kind: record.kind, title: record.title, updated: now, savedAt: now, persistedAt: now,
      persistedVersion: crypto.randomUUID(), revision: record.revision || crypto.randomUUID(), saveMode: 'saved', source: 'local-disk', storageVersion: 'local-disk-v1'};
    if (typeof meta.revision !== 'string' || meta.revision.length > 160) throw Error('工程版本无效。');
    for (const key of ['width', 'height']) if (Number.isFinite(record.doc[key]) && record.doc[key] > 0 && record.doc[key] <= 1000000) meta[key] = record.doc[key];
    if (record.thumbnail !== undefined) {
      if (typeof record.thumbnail !== 'string' || record.thumbnail.length > 48 * 1024 || !/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(record.thumbnail))
        throw Error('工程封面格式无效或超过48KiB限制。');
      meta.thumbnail = record.thumbnail; meta.thumbnailRevision = meta.revision;
    }
    const saved = {...record, ...meta}; delete saved._expectedVersion; delete saved._expectedDirectory;
    const packed = ShijieProjectCodec.encode(saved);
    const raw = new TextEncoder().encode(JSON.stringify({wireFormat: 'shijie-image-table', wireVersion: 1, job: packed.doc, images: packed.images}));
    if (raw.byteLength > fileLimit) throw Error('工程文件超过容量限制。');
    const header = new TextEncoder().encode(JSON.stringify(meta) + '\n');
    if (header.byteLength > headerLimit) throw Error('工程索引过大，原工程已保留。');
    const compressed = await new Response(new Blob([raw]).stream().pipeThrough(new CompressionStream('gzip'))).blob();
    const output = new Blob([header, compressed]);
    // Recheck after compression; an external editor can have changed the file meanwhile.
    await current(folder.id);
    const latest = await entries(folder.handle);
    checkVersion(latest.projects.get(ident), record._expectedVersion);
    const name = filename(record.title, latest.names, latest.projects.get(ident), ['manual', 'ai'].includes(record.doc._titleSource) && record.title !== previous?.meta.title);
    const created = !latest.names.has(name.toLocaleLowerCase());
    const target = await folder.handle.getFileHandle(name, {create: true});
    let writer;
    try {
      writer = await target.createWritable();
      await writer.write(output);
      // Permission revocation or account/directory changes never get a save acknowledgement.
      await current(folder.id);
      checkVersion((await entries(folder.handle)).projects.get(ident), record._expectedVersion);
      await writer.close();
      writer = null;
      const written = await target.getFile();
      const digest = async blob => new Uint8Array(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())).join(',');
      if (written.size !== output.size || await digest(written) !== await digest(output)) throw Error('本地工程写入后核对失败；当前编辑保留，请重试或导出工程。');
      if (previous && previous.name !== name) {
        checkVersion({meta: (await readHeader(await previous.handle.getFile())).meta}, record._expectedVersion);
        await folder.handle.removeEntry(previous.name);
      }
      await current(folder.id);
      return {project: meta, directory: folder.id, directoryName: folder.handle.name};
    } catch (error) {
      if (writer) await writer.abort().catch(() => {});
      // A failed new writer may leave an empty placeholder. Never remove completed bytes.
      if (created) try { if ((await target.getFile()).size === 0) await folder.handle.removeEntry(name); } catch {}
      throw error;
    }
  }
  async function request(path, options = {}) {
    available();
    const url = new URL(path, 'https://local.invalid'), method = (options.method || 'GET').toUpperCase();
    const body = options.body ? unpack(JSON.parse(options.body)) : {};
    if (url.pathname === '/saved-projects/settings/location') throw Error('请点击“选择本地文件夹”，不能输入服务器路径。');
    return navigator.locks.request(lockName, async () => {
      const expected = body._expectedDirectory || url.searchParams.get('directory');
      const folder = await current(expected, url.pathname !== '/saved-projects');
      if (url.pathname === '/saved-projects' && method === 'GET') {
        const listing = folder ? await entries(folder.handle) : {projects: new Map(), unreadable: 0};
        return {directory: folder?.id || null, directoryName: folder?.handle.name || '',
          projects: [...listing.projects.values()].map(entry => entry.meta).sort((a, b) => b.updated - a.updated), unreadable: listing.unreadable};
      }
      const ident = decodeURIComponent(url.pathname.slice('/saved-projects/'.length)); validId(ident);
      if (!folder) throw Error('请先选择本地工程文件夹。');
      if (method === 'PUT' || method === 'DELETE') {
        if (!expected || expected !== folder.id) throw directoryChanged();
      }
      if (method === 'PUT') return save(folder, ident, body);
      const entry = (await entries(folder.handle)).projects.get(ident);
      if (method === 'GET') {
        if (!entry) { const error = Error('此工程已从所选文件夹移走或删除。'); error.status = 404; throw error; }
        const project = await readProject(await entry.handle.getFile(), ident);
        await current(folder.id);
        return {project, directory: folder.id, directoryName: folder.handle.name};
      }
      if (method === 'DELETE') {
        checkVersion(entry, body._expectedVersion);
        if (entry) await folder.handle.removeEntry(entry.name);
        return {deleted: true, directory: folder.id};
      }
      throw Error('此本地工程操作不受支持；工程不会改存服务器。');
    });
  }
  window.ShijieBrowserProjects = {supported, pickDirectory, setDirectory, request,
    directoryName: () => selection?.handle.name || '', unsupportedMessage: unsupported};
})();
