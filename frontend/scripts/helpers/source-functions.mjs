import { readFileSync } from "node:fs";
import ts from "typescript";

// Exercise the actual private Next page/action functions, without booting Next or
// exporting server-only internals into the client bundle. Only IO is injected.
export function sourceFunctions(url, names, bindings = {}) {
  const source = readFileSync(url, "utf8");
  const ast = ts.createSourceFile(url.pathname, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const topLevel = new Map(ast.statements.filter(ts.isFunctionDeclaration).filter(x => x.name).map(x => [x.name.text, x]));
  const selected = new Map();
  function include(name) {
    if (selected.has(name) || name in bindings) return;
    let node = topLevel.get(name);
    if (!node && names.includes(name)) {
      function find(child) {
        if (ts.isFunctionDeclaration(child) && child.name?.text === name) node = child;
        else ts.forEachChild(child, find);
      }
      find(ast);
    }
    if (!node) throw new Error("Source function missing: " + name);
    selected.set(name, node.getText(ast).replace(/^export (default )?/, ""));
    function visit(child) {
      if (ts.isIdentifier(child) && topLevel.has(child.text)) include(child.text);
      ts.forEachChild(child, visit);
    }
    visit(node);
  }
  names.forEach(include);
  const code = ts.transpileModule([...selected.values()].join("\n"), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  return new Function(...Object.keys(bindings), code + "\nreturn {" + names.join(",") + "};")(...Object.values(bindings));
}
