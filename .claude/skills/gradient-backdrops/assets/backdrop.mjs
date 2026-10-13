// ES module entry. Copy this next to backdrop.js and import from it:
//   import { createBackdrop } from './backdrop.mjs';
import './backdrop.js';

const GB = globalThis.GradientBackdrop;

export const {
  createBackdrop, autoInit, cssBackdrop, grainURL, parseColor, srgbToOklab,
  STYLES, PRESETS, CSS_PRESETS, PRELUDE,
} = GB;
export default GB;
