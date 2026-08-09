// Bundle once, render a list of review stills. Much faster than N `remotion still` calls.
import {bundle} from '@remotion/bundler';
import {selectComposition, renderStill} from '@remotion/renderer';
import path from 'node:path';
import fs from 'node:fs';

const times = (process.argv[2] ?? '1.4,5,9,14.6,20,26.6,31.5,40,48.2,55,62')
  .split(',').map(Number);
const outDir = process.argv[3] ?? '/home/claude/hp/remotion/out/stills';
fs.mkdirSync(outDir, {recursive: true});

const serveUrl = await bundle({entryPoint: path.resolve('src/index.ts')});
const composition = await selectComposition({serveUrl, id: 'SewerSpider', inputProps: {withAudio: false}});
for (const t of times) {
  const frame = Math.round(t * composition.fps);
  const output = path.join(outDir, `t${t.toFixed(2)}.png`);
  await renderStill({
    composition, serveUrl, output, frame, inputProps: {withAudio: false},
    chromiumOptions: {gl: 'swangle'}, overwrite: true, imageFormat: 'png',
  });
  console.log(output);
}
