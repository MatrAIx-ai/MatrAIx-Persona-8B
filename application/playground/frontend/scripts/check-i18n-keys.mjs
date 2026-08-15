import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import ts from "typescript";

const root = process.cwd();
const sourcePath = path.join(root, "src", "i18n", "messages", "en-US.json");
const sourceCatalog = JSON.parse(fs.readFileSync(sourcePath, "utf8"));
const knownKeys = new Set(Object.keys(sourceCatalog));
const errors = [];

function visitFiles(directory) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) visitFiles(target);
    else if (/\.(ts|tsx)$/.test(entry.name) && !entry.name.endsWith(".test.ts") && !entry.name.endsWith(".test.tsx")) {
      checkFile(target);
    }
  }
}

function checkFile(filePath) {
  const text = fs.readFileSync(filePath, "utf8");
  const sourceFile = ts.createSourceFile(
    filePath,
    text,
    ts.ScriptTarget.Latest,
    true,
    filePath.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const relativePath = path.relative(root, filePath).replaceAll("\\", "/");
  const isI18nAdapter = relativePath === "src/i18n/I18nProvider.tsx";

  function visit(node) {
    if (
      ts.isImportDeclaration(node) &&
      ts.isStringLiteral(node.moduleSpecifier) &&
      node.moduleSpecifier.text === "react-intl" &&
      !isI18nAdapter
    ) {
      const location = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
      errors.push(
        `${relativePath}:${location.line + 1}:${location.character + 1} import from react-intl bypasses the typed useI18n() adapter`,
      );
    }

    const isTranslationCall =
      ts.isCallExpression(node) &&
      ((ts.isIdentifier(node.expression) && node.expression.text === "t") ||
        (ts.isPropertyAccessExpression(node.expression) && node.expression.name.text === "t"));
    if (
      isTranslationCall &&
      node.arguments.length > 0
    ) {
      const keyNode = node.arguments[0];
      if (ts.isStringLiteralLike(keyNode) && !knownKeys.has(keyNode.text)) {
        const location = sourceFile.getLineAndCharacterOfPosition(keyNode.getStart(sourceFile));
        errors.push(
          `${relativePath}:${location.line + 1}:${location.character + 1} missing English key ${JSON.stringify(keyNode.text)}`,
        );
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
}

visitFiles(path.join(root, "src"));

if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log(`i18n source catalog OK (${knownKeys.size} keys)`);
