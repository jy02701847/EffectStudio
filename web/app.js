/* 效果图优化 · 本地版前端（无框架、无构建） */
var $ = function (id) { return document.getElementById(id); };
var files = [];
var results = [];
var batchId = '';
var nrReady = false;

function b64(s) {
  return btoa(String.fromCharCode.apply(null, new TextEncoder().encode(s)));
}
function unb64(s) {
  return new TextDecoder().decode(Uint8Array.from(atob(s), function (c) { return c.charCodeAt(0); }));
}
function say(s) { $('log').textContent = s; }
function progress(s) { $('progress').textContent = s; }

function strength() {
  var p = parseFloat($('power').value);
  return { contrast: 1.35 * p, shadowhl: 1.35 * p, color: 1.25 * p,
           clarity: parseFloat($('clarity').value), radius_div: 300.0,
           wb: parseFloat($('wb').value) };
}

fetch('/api/health').then(function (r) { return r.json(); }).then(function (d) {
  nrReady = !!(d.nr && d.nr.available);
  $('status').className = 'status ' + (nrReady ? 'ok' : 'warn');
  $('status').textContent = nrReady ? '服务正常 · 神经网络可用' : '服务正常 · 神经网络未配置';
  if (!nrReady) { $('optNr').checked = false; $('optNr').disabled = true; }
}).catch(function (e) {
  $('status').className = 'status warn';
  $('status').textContent = '服务未连接';
  say('健康检查失败: ' + e.message);
});

$('power').oninput = function () { $('powerVal').textContent = parseFloat(this.value).toFixed(2); };
$('clarity').oninput = function () { $('clarityVal').textContent = parseFloat(this.value).toFixed(2); };
$('wb').oninput = function () { $('wbVal').textContent = this.value; };

function setFiles(list) {
  files = Array.prototype.slice.call(list).filter(function (f) { return /^image\//.test(f.type) || /\.(png|jpe?g|bmp|tiff?|webp)$/i.test(f.name); });
  $('filelist').textContent = files.length ? ('已选 ' + files.length + ' 张：' + files.map(function (f) { return f.name; }).join('、')) : '';
}
$('file').onchange = function () { setFiles(this.files); };
var drop = $('drop');
drop.ondragover = function (e) { e.preventDefault(); drop.classList.add('over'); };
drop.ondragleave = function () { drop.classList.remove('over'); };
drop.ondrop = function (e) { e.preventDefault(); drop.classList.remove('over'); setFiles(e.dataTransfer.files); };

$('split').oninput = function () {
  var v = this.value;
  $('beforeWrap').style.clipPath = 'inset(0 ' + (100 - v) + '% 0 0)';
  $('divider').style.left = v + '%';
};

function showSingle(item) {
  $('result').hidden = false;
  $('imgBefore').src = item.beforeUrl;
  $('imgAfter').src = item.afterUrl;
  $('download').href = '/api/result/' + item.meta.id;
  $('download').setAttribute('download', item.meta.name.replace(/\.[^.]+$/, '') + '_优化.png');
  var s = item.meta.seconds;
  $('cost').textContent = item.meta.size[0] + '×' + item.meta.size[1] + ' · 调色 ' + s.auto +
    's' + (item.meta.nr ? ' · 净化 ' + s.nr + 's' : '') + ' · 共 ' + s.total + 's' +
    (item.meta.nr_note ? ' · ' + item.meta.nr_note.slice(0, 40) : '');
  var p = item.meta.params;
  var names = { exposure: '曝光', contrast: '对比', shadows: '阴影', highlights: '高光',
                vibrance: '自然饱和', saturation: '饱和', temperature: '色温',
                dehaze: '去雾', clarity: '清晰度', sharpen_amount: '锐化' };
  $('params').innerHTML = Object.keys(names).map(function (k) {
    return '<span>' + names[k] + ' ' + p[k] + '</span>';
  }).join('');
}

function showGrid() {
  var g = $('grid');
  g.hidden = false;
  g.innerHTML = results.map(function (it) {
    return '<div class="card"><img src="' + it.afterUrl + '"><p>' + it.meta.name + '</p>' +
      '<a href="/api/result/' + it.meta.id + '" download="' +
      it.meta.name.replace(/\.[^.]+$/, '') + '_优化.png">下载原尺寸 PNG</a></div>';
  }).join('');
}

$('run').onclick = async function () {
  if (!files.length) { say('请先选一张图'); return; }
  var multi = files.length > 1;
  batchId = multi ? ('b' + Date.now().toString(36)) : '';
  var opts = { auto: $('optAuto').checked, nr: $('optNr').checked, strength: strength() };
  $('run').disabled = true;
  results = [];
  $('result').hidden = true;
  $('grid').hidden = true;
  $('zip').disabled = true;
  try {
    for (var i = 0; i < files.length; i++) {
      var f = files[i];
      progress('处理中 ' + (i + 1) + '/' + files.length + '：' + f.name +
               ($('optNr').checked ? '（含神经净化，大图约 1 分钟）' : ''));
      var raw = await f.arrayBuffer();
      var headers = { 'Content-Type': 'application/octet-stream',
                      'X-Opts': b64(JSON.stringify(opts)),
                      'X-Name': b64(f.name) };
      if (batchId) headers['X-Batch'] = batchId;
      var r = await fetch('/api/process', { method: 'POST', body: raw, headers: headers });
      if (!r.ok) throw new Error(f.name + '：' + (await r.text()));
      var meta = JSON.parse(unb64(r.headers.get('X-Meta')));
      var afterUrl = URL.createObjectURL(await r.blob());
      var item = { meta: meta, afterUrl: afterUrl, beforeUrl: URL.createObjectURL(f) };
      results.push(item);
      if (!multi) showSingle(item);
      say('完成 ' + (i + 1) + '/' + files.length + ' · ' + f.name + ' · ' + meta.seconds.total + 's');
    }
    if (multi) { showGrid(); $('zip').disabled = false; }
    progress('完成 ' + files.length + ' 张');
  } catch (e) {
    say('失败：' + e.message);
    progress('');
  } finally {
    $('run').disabled = false;
  }
};

$('zip').onclick = function () {
  if (batchId) window.location.href = '/api/zip/' + batchId;
};
$('clear').onclick = function () {
  files = []; results = []; batchId = '';
  $('file').value = ''; $('filelist').textContent = '';
  $('result').hidden = true; $('grid').hidden = true; $('zip').disabled = true;
  progress(''); say('已清空');
};
