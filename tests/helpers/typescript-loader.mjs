import { readFile } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import ts from "typescript";

let mocks = {};

export function initialize(data = {}) {
  mocks = data.mocks ?? {};
}

export async function resolve(specifier, context, nextResolve) {
  if (mocks[specifier]) return { url: mocks[specifier], shortCircuit: true };
  if (specifier.startsWith("@/")) specifier = pathToFileURL(`${process.cwd()}/${specifier.slice(2)}`).href;
  try {
    return await nextResolve(specifier, context);
  } catch (error) {
    if (!specifier.startsWith(".") && !specifier.startsWith("file:") && !specifier.startsWith("next/")) throw error;
    for (const suffix of [".ts", ".tsx", "/index.ts", ".js"]) {
      try {
        return await nextResolve(`${specifier}${suffix}`, context);
      } catch {
        // Try the next TypeScript or Next.js extension.
      }
    }
    throw error;
  }
}

export async function load(url, context, nextLoad) {
  if (!/\.tsx?(?:\?|$)/.test(url)) return nextLoad(url, context);
  const source = await readFile(new URL(url), "utf8");
  const result = ts.transpileModule(source, {
    fileName: fileURLToPath(url),
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX },
  });
  return { format: "module", source: result.outputText, shortCircuit: true };
}
