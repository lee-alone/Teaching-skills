// LaTeX -> SVG / PNG（MathJax tex-svg + resvg），用于公式的矢量降级输出。
//
// 用法：
//   node mathjax_tex2svg.js < input.json > output.json
//
// 输入：
//   {"outDir":"C:/tmp/math","items":[
//      {"id":"f1","latex":"x^2","display":false,"color":"1F3864","raster":true,"pngScale":4}]}
//
// 输出：
//   {"results":[{"id":"f1","ok":true,"svg":"<svg .../>","svgPath":"...","pngPath":"...",
//                "width":120.5,"height":24.3}]}
//
// 输出 SVG 的字形为 <path>，不依赖任何字体，放大不失真。

require('mathjax-full/js/util/entities/all.js');

const fs = require('fs');
const path = require('path');
const { mathjax } = require('mathjax-full/js/mathjax.js');
const { TeX } = require('mathjax-full/js/input/tex.js');
const { SVG } = require('mathjax-full/js/output/svg.js');
const { liteAdaptor } = require('mathjax-full/js/adaptors/liteAdaptor.js');
const { RegisterHTMLHandler } = require('mathjax-full/js/handlers/html.js');
const { AllPackages } = require('mathjax-full/js/input/tex/AllPackages.js');

let Resvg = null;
try {
  Resvg = require('@resvg/resvg-js').Resvg;
} catch (e) {
  // 未安装光栅化库时只输出 SVG，由调用方决定是否降级
}

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);

const tex = new TeX({ packages: AllPackages });
const svg = new SVG({ fontCache: 'local' });
const doc = mathjax.document('', { InputJax: tex, OutputJax: svg });

function safeName(id, i) {
  const base = String(id || 'eq' + i).replace(/[^\w\u4e00-\u9fff-]+/g, '_');
  return base || 'eq' + i;
}

function main() {
  let payload;
  try {
    payload = JSON.parse(fs.readFileSync(0, 'utf-8'));
  } catch (e) {
    process.stdout.write(JSON.stringify({ error: 'invalid input json: ' + e.message }));
    return;
  }

  const items = payload.items || [];
  const outDir = payload.outDir || null;
  if (outDir) fs.mkdirSync(outDir, { recursive: true });

  const results = [];

  items.forEach((it, i) => {
    const id = it.id || 'eq' + i;
    const rec = { id };
    try {
      const node = doc.convert(it.latex, {
        display: !!it.display,
        em: 16,
        ex: 8,
        containerWidth: 100 * 16,
      });

      let inner = adaptor.innerHTML(node);
      const wMatch = inner.match(/width="([\d.]+)ex"/);
      const hMatch = inner.match(/height="([\d.]+)ex"/);
      const vMatch = inner.match(/viewBox="([^"]+)"/);
      const ex = 8;
      const pxW = wMatch ? Math.max(1, Math.round(parseFloat(wMatch[1]) * ex * 100) / 100) : 1;
      const pxH = hMatch ? Math.max(1, Math.round(parseFloat(hMatch[1]) * ex * 100) / 100) : 1;

      // 取出基线偏移（vertical-align），供调用方做行内对齐
      const vaMatch = inner.match(/vertical-align:\s*(-?[\d.]+)ex/);
      const descent = vaMatch ? Math.abs(parseFloat(vaMatch[1])) * 8 : 0;

      // 去掉 MathJax 自带的 ex 尺寸、样式与命名空间声明，改由本脚本统一重建根属性
      // 注意：inner 仍保留结尾的 ">"，拼接时不可再补一个 ">"
      inner = inner.replace(/^<svg\s+/, '').replace(/<\/svg>\s*$/, '');
      inner = inner.replace(/\sxmlns(:\w+)?="[^"]*"/g, '');
      inner = inner.replace(/\sstyle="[^"]*"/g, '');
      inner = inner.replace(/\s(width|height)="[\d.]+(ex|px|em)"/g, '');

      const attrs = [
        'xmlns="http://www.w3.org/2000/svg"',
        'xmlns:xlink="http://www.w3.org/1999/xlink"',
        'width="' + pxW + '"',
        'height="' + pxH + '"',
        it.color ? 'style="color:#' + String(it.color).replace('#', '') + '"' : '',
      ].filter(Boolean).join(' ');

      const svgText = '<svg ' + attrs + ' ' + inner + '</svg>';
      rec.ok = true;
      rec.svg = svgText;
      rec.width = pxW;
      rec.height = pxH;
      rec.descent = descent;
      rec.viewBox = vMatch ? vMatch[1] : null;

      if (outDir) {
        const stem = safeName(id, i);
        const svgPath = path.join(outDir, stem + '.svg');
        fs.writeFileSync(svgPath, svgText, 'utf-8');
        rec.svgPath = svgPath;

        if (it.raster && Resvg) {
          const scale = Math.max(1, Number(it.pngScale) || 4);
          const r = new Resvg(svgText, {
            fitTo: { mode: 'zoom', value: scale },
            background: 'rgba(0,0,0,0)',
          });
          const png = r.render().asPng();
          const pngPath = path.join(outDir, stem + '.png');
          fs.writeFileSync(pngPath, png);
          rec.pngPath = pngPath;
        }
      }
    } catch (e) {
      rec.ok = false;
      rec.error = String(e && e.message ? e.message : e);
    }
    results.push(rec);
  });

  process.stdout.write(JSON.stringify({ results, rasterizer: !!Resvg }));
}

main();
