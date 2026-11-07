/** Fixed reasoning/progress/text replay. Measures isolated render/derivation CPU, not browser FPS. */
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { performance } from 'node:perf_hooks';
import { createRequire } from 'node:module';
import vm from 'node:vm';
const require = createRequire(import.meta.url);
const ts = require('typescript');
const root = new URL('../../', import.meta.url);
const args = process.argv.slice(2);
let baselineRef = '573d69a';
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--baseline-ref' && args[i + 1]) baselineRef = args[++i];
  else if (args[i].startsWith('--baseline-ref=')) baselineRef = args[i].slice('--baseline-ref='.length);
  else throw new Error('Usage: node web/scripts/benchmark-story-render.mjs [--baseline-ref <git-ref>]');
}
const baselineCommit = execFileSync('git', ['rev-parse', '--verify', '--end-of-options', `${baselineRef}^{commit}`], { cwd: root, encoding: 'utf8' }).trim();
const oldSource = execFileSync('git', ['show', `${baselineCommit}:web/components/StoryMarkdown.tsx`], { cwd: root, encoding: 'utf8' });
const newSource = readFileSync(new URL('../components/StoryMarkdown.tsx', import.meta.url), 'utf8');
const charactersSource = readFileSync(new URL('../lib/characters.ts', import.meta.url), 'utf8');
function load(source, dependencies) {
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020 } }).outputText;
  const loaded = { exports: {} };
  vm.runInThisContext(`(function(require,module,exports){${code}\n})`)(name => dependencies[name] ?? require(name), loaded, loaded.exports);
  return loaded.exports;
}
function renderer(source) {
  const slots = []; let slot = 0; let matcherBuilds = 0; let componentRenders = 0;
  const characters = load(charactersSource, {});
  const useMemo = (compute, deps) => {
    const at = slot++; const previous = slots[at];
    if (previous && deps.length === previous.deps.length && deps.every((v, i) => Object.is(v, previous.deps[i]))) return previous.value;
    const value = compute(); slots[at] = { deps, value }; return value;
  };
  const memo = component => {
    let previous; let result;
    return props => {
      if (previous && Object.keys(props).length === Object.keys(previous).length && Object.keys(props).every(key => Object.is(props[key], previous[key]))) return result;
      previous = props; return result = component(props);
    };
  };
  const jsx = (type, props) => typeof type === 'function' ? type(props) : { type, props };
  const wrapped = source.replace('const blocks =', 'globalThis.__storyBenchmarkRender(); const blocks =');
  const component = load(wrapped, {
    react: { useMemo, memo },
    'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: Symbol.for('fragment') },
    '@/lib/characters': { ...characters, buildCharacterMatchers: (...args) => { matcherBuilds++; return characters.buildCharacterMatchers(...args); } }
  }).StoryMarkdown;
  return {
    run(props) { slot = 0; globalThis.__storyBenchmarkRender = () => componentRenders++; component(props); },
    stats: () => ({ componentRenders, matcherBuilds })
  };
}
const characters = Array.from({ length: 24 }, (_, i) => ({ id: `c${i}`, name: `人物${i}`, aliases: [`角色${i}`], is_visible: true }));
const text = Array.from({ length: 240 }, (_, i) => `### 场景${i}\n\n人物${i % 24}走进旧车站，**铜钥匙**留在掌心。\n\n雨落在站台上，角色${(i + 1) % 24}回头观察门外的脚步。\n\n`).join('');
const click = () => {};
const frames = Array.from({ length: 1200 }, (_, i) => ({ content: text.slice(0, 1000 + Math.floor(i / 10) * 80), characters, onCharacterClick: click, showCaret: true }));
function measure(source) {
  const render = renderer(source); const start = performance.now(); for (const frame of frames) render.run(frame);
  return { ms: performance.now() - start, ...render.stats() };
}
for (let i = 0; i < 2; i++) { measure(oldSource); measure(newSource); }
const before = [], after = [];
for (let i = 0; i < 7; i++) { before.push(measure(oldSource)); after.push(measure(newSource)); }
const median = values => [...values].sort((a,b) => a-b)[Math.floor(values.length / 2)];
const summarize = values => ({ medianMs: +median(values.map(x => x.ms)).toFixed(2), componentRenders: values[0].componentRenders, matcherBuilds: values[0].matcherBuilds });
console.log(JSON.stringify({ baseline: { ref: baselineRef, commit: baselineCommit }, node: process.version, frames: frames.length, textUpdates: 120, finalChars: frames.at(-1).content.length, characters: characters.length, trials: 7, before: summarize(before), after: summarize(after), scope: 'isolated component/derivation replay with a shallow memo/useMemo harness; excludes React reconciliation, DOM, network and model latency' }, null, 2));
delete globalThis.__storyBenchmarkRender;
