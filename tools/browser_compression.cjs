/* Bounded local-only gzip reading for browsers without DecompressionStream. */
const {Inflate} = require('pako');
async function readGzip(file, limit) {
  if (!file || !Number.isSafeInteger(limit) || limit < 1 || file.size > limit) throw Error('工程文件超过容量限制。');
  const input = new Uint8Array(await file.arrayBuffer());
  if (input[0] !== 31 || input[1] !== 139 || input[2] !== 8) throw Error('本地工程压缩格式无效，原文件已保留。');
  const inflate = new Inflate({chunkSize: 32768}), decoder = new TextDecoder('utf-8', {fatal:true});
  let length = 0, text = '';
  inflate.onData = chunk => {
    length += chunk.byteLength;
    if (length > limit) throw Error('工程解压后超过容量限制。');
    text += decoder.decode(chunk, {stream:true});
  };
  inflate.push(input, true);
  if (inflate.err || !inflate.ended) throw Error('本地工程压缩内容损坏或不完整，原文件已保留。');
  return text + decoder.decode();
}
module.exports = {readGzip};
