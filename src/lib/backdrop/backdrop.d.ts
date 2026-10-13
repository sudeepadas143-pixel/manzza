// Types for backdrop.js / backdrop.mjs

export type StyleName =
  | 'flow' | 'mesh' | 'aurora' | 'silk' | 'sky' | 'waves' | 'mist' | 'bars'
  | 'prism' | 'rings' | 'glow' | 'stripes' | 'forms' | 'watercolor' | 'swirl';

export type ParamValue = number | boolean | number[] | number[][];

export interface BackdropOptions {
  /** A key of PRESETS. Its style/colors/params are used as the base. */
  preset?: string;
  style?: StyleName | string;
  /** 2–6 CSS colours (hex, rgb(), hsl(), oklch(), names). Order matters per style. */
  colors?: string[];
  /** Style-specific knobs; see STYLES[style].params. */
  params?: Record<string, ParamValue>;
  /** Animation speed multiplier. 0 freezes the motion. Default 1. */
  speed?: number;
  /** Film grain overlay opacity 0..1. Default 0. ~0.1–0.25 is typical. */
  grain?: number;
  /** Varies the composition without changing the look. Default 0. */
  seed?: number;
  /** false renders a single still frame. Default true. */
  animate?: boolean;
  /** Freeze when the OS asks for reduced motion. Default true. */
  respectReducedMotion?: boolean;
  /** Render scale relative to CSS px × DPR (≤2). Default per style (0.35–1). */
  quality?: number;
  /** Hard cap on rendered pixels. Default 2.4 million. */
  maxPixels?: number;
  /** Start time offset in seconds. */
  time?: number;
  /**
   * 'direct' = own WebGL context on the visible canvas (fastest, the default while
   * under 12 per page); 'shared' = render in one hidden context and copy (needed only
   * for many simultaneous backdrops; slower in Safari); 'auto' picks. Default 'auto'.
   */
  mode?: 'auto' | 'direct' | 'shared';
}

export interface Backdrop {
  el: HTMLElement;
  canvas: HTMLCanvasElement;
  opts: Required<BackdropOptions>;
  time: number;
  paused: boolean;
  /** Which renderer this backdrop ended up with. */
  readonly mode: 'direct' | 'shared';
  /** Merge new options (colours, params, style, speed, grain…) and re-render. */
  set(next: BackdropOptions): Backdrop;
  play(): Backdrop;
  pause(): Backdrop;
  toggle(): Backdrop;
  render(): Backdrop;
  isPlaying(): boolean;
  /** Current frame as a data URL (render resolution). */
  snapshot(type?: string, quality?: number): string;
  destroy(): void;
}

export interface StyleSpec {
  label: string;
  order: string;
  quality: number;
  params: Record<string, [number, number, number, number] | { value: ParamValue }>;
  frag: string;
}

export function createBackdrop(target: string | HTMLElement, options?: BackdropOptions): Backdrop;
export function autoInit(root?: ParentNode): Backdrop[];
export function cssBackdrop(
  kind: 'mesh' | 'linear' | 'ios' | 'conic' | 'retro' | string,
  colors?: string[],
  opts?: { angle?: number; points?: [number, number][] }
): string;
export function grainURL(): string;
export function parseColor(c: string | number[]): [number, number, number];
export function srgbToOklab(rgb: [number, number, number]): [number, number, number];
export const STYLES: Record<string, StyleSpec>;
export const PRESETS: Record<string, { style: StyleName; colors: string[]; params?: Record<string, ParamValue> }>;
export const CSS_PRESETS: Record<string, { kind: string; colors: string[]; grain?: number }>;
export const PRELUDE: string;

declare const GradientBackdrop: {
  createBackdrop: typeof createBackdrop;
  autoInit: typeof autoInit;
  cssBackdrop: typeof cssBackdrop;
  grainURL: typeof grainURL;
  parseColor: typeof parseColor;
  srgbToOklab: typeof srgbToOklab;
  STYLES: typeof STYLES;
  PRESETS: typeof PRESETS;
  CSS_PRESETS: typeof CSS_PRESETS;
  PRELUDE: string;
};
export default GradientBackdrop;

declare global {
  // eslint-disable-next-line no-var
  var GradientBackdrop: typeof import('./backdrop').default;
}
