import {loadFont} from '@remotion/fonts';
import {staticFile, continueRender, delayRender} from 'remotion';

const FACES: [string, string, number][] = [
  ['Anton', 'fonts/anton-latin-400-normal.ttf', 400],
  ['ArchivoBlack', 'fonts/archivo-black-latin-400-normal.ttf', 400],
  ['Bangers', 'fonts/bangers-latin-400-normal.ttf', 400],
  ['Inter', 'fonts/inter-latin-400-normal.ttf', 400],
  ['Inter', 'fonts/inter-latin-700-normal.ttf', 700],
  ['Inter', 'fonts/inter-latin-900-normal.ttf', 900],
];

let started = false;
export const ensureFonts = () => {
  if (started) return;
  started = true;
  const handle = delayRender('loading house fonts');
  Promise.all(
    FACES.map(([family, file, weight]) =>
      loadFont({family, url: staticFile(file), weight: String(weight), format: 'truetype'}),
    ),
  )
    .then(() => document.fonts.ready)
    .then(() => continueRender(handle))
    .catch((e) => {
      console.error(e);
      continueRender(handle);
    });
};
