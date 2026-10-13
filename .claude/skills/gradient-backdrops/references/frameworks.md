# Framework integration

Copy `assets/backdrop.js`, `assets/backdrop.mjs` and `assets/backdrop.d.ts` into the
project (e.g. `src/lib/backdrop/`). The runtime is browser-only, so mount it on the client.

## React / Next.js

```tsx
// src/components/Backdrop.tsx
'use client';
import { useEffect, useRef } from 'react';
import { createBackdrop, type BackdropOptions, type Backdrop as BD } from '@/lib/backdrop/backdrop.mjs';

type Props = BackdropOptions & React.HTMLAttributes<HTMLDivElement> & { children?: React.ReactNode };

export function Backdrop({ preset, style, colors, params, speed, grain, seed, animate, quality, children, ...rest }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const bd = useRef<BD | null>(null);

  useEffect(() => {
    bd.current = createBackdrop(ref.current!, { preset, style, colors, params, speed, grain, seed, animate, quality });
    return () => bd.current?.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // live-update without remounting
  useEffect(() => {
    bd.current?.set({ ...(preset ? { preset } : {}), style, colors, params, speed, grain, seed, animate });
  }, [preset, style, JSON.stringify(colors), JSON.stringify(params), speed, grain, seed, animate]);

  return <div ref={ref} {...rest}>{children}</div>;
}
```

```tsx
<Backdrop preset="iridescent-cloud" grain={0.12} className="min-h-svh grid place-items-center">
  <h1 className="text-8xl font-serif text-[#1F1B2E]">Sonorous</h1>
</Backdrop>
```

For TypeScript path imports of the `.mjs` with types, add a sibling `backdrop.mjs.d.ts` that
re-exports `./backdrop` (or rename `backdrop.d.ts` to `backdrop.mjs.d.ts`).

Next.js App Router: the `'use client'` directive is required. With the Pages Router, use
`dynamic(() => import('…/Backdrop'), { ssr: false })` if you see `document is not defined`.

## Vue 3 / Nuxt

```vue
<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue';
import { createBackdrop } from '@/lib/backdrop/backdrop.mjs';
const props = defineProps<{ preset?: string; style?: string; colors?: string[]; params?: Record<string, any>; grain?: number; speed?: number }>();
const el = ref<HTMLElement>();
let bd: any;
onMounted(() => { bd = createBackdrop(el.value!, { ...props }); });
watch(() => ({ ...props }), (p) => bd?.set(p), { deep: true });
onBeforeUnmount(() => bd?.destroy());
</script>
<template><div ref="el"><slot /></div></template>
```
In Nuxt, wrap usage in `<ClientOnly>` or name the file `Backdrop.client.vue`.

## Svelte / SvelteKit

```svelte
<script>
  import { onMount } from 'svelte';
  import { createBackdrop } from '$lib/backdrop/backdrop.mjs';
  export let options = { preset: 'night-swim' };
  let el, bd;
  onMount(() => { bd = createBackdrop(el, options); return () => bd.destroy(); });
  $: bd && bd.set(options);
</script>
<div bind:this={el} class={$$props.class}><slot /></div>
```
Or as an action: `use:backdrop={{ preset: 'tidal' }}` with
`export const backdrop = (node, o) => { const b = createBackdrop(node, o); return { update: (n) => b.set(n), destroy: () => b.destroy() }; };`

## Astro

Use the declarative API. It needs no framework island:
```astro
<section class="hero" data-backdrop="field-notes" data-grain="0.1">…</section>
<script>import '../lib/backdrop/backdrop.js';</script>
```
Astro bundles the script and the runtime auto-mounts `[data-backdrop]`. For elements added later
(view transitions), call `GradientBackdrop.autoInit()` in an `astro:page-load` listener.

## Plain HTML / static sites / WordPress / Webflow

```html
<section data-backdrop="aurora" data-colors="#EDFFEB #5FE896 #2E7A6A #132B45">…</section>
<script src="/js/backdrop.js" defer></script>
```
In Webflow, add the script in Page Settings → Before `</body>` and put `data-backdrop` as a custom attribute.

## Tailwind

The runtime handles positioning itself. Just give the host a size:
```html
<section data-backdrop="fluid" class="relative isolate min-h-svh grid place-items-center">…</section>
```
For the static fallback, use an arbitrary value:
`bg-[radial-gradient(80%_70%_at_20%_20%,#9BE0E8,transparent_60%),radial-gradient(80%_70%_at_80%_80%,#F8B8D9,transparent_60%),#F6F9FF]`.

## Exporting a still for OG images / social

```js
const bd = createBackdrop(offscreenDiv, { preset: 'amethyst', animate: false, quality: 1 });
// offscreenDiv sized e.g. 1200×630 CSS px
const png = bd.snapshot('image/png');  // data URL at render resolution
```
Typography isn't in the canvas. For a finished poster, draw it onto a 2D canvas after `drawImage`,
or screenshot the DOM with Playwright.
