import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import ts from "typescript";

const root = process.cwd();
const sourcePath = path.join(root, "src", "i18n", "messages", "en-US.json");
const sourceCatalog = JSON.parse(fs.readFileSync(sourcePath, "utf8"));
const knownKeys = new Set(Object.keys(sourceCatalog));
const errors = [];

function unwrapExpression(node) {
  let current = node;
  while (
    ts.isParenthesizedExpression(current) ||
    ts.isAsExpression(current) ||
    ts.isTypeAssertionExpression(current) ||
    ts.isNonNullExpression(current) ||
    ts.isSatisfiesExpression(current)
  ) {
    current = current.expression;
  }
  return current;
}

function isAllowedTranslationKeyExpression(node, explicitMessageMaps) {
  const expression = unwrapExpression(node);
  if (ts.isStringLiteralLike(expression)) return true;
  if (ts.isElementAccessExpression(expression)) {
    const map = unwrapExpression(expression.expression);
    return ts.isIdentifier(map) && explicitMessageMaps.has(map.text);
  }
  if (ts.isPropertyAccessExpression(expression)) {
    const map = unwrapExpression(expression.expression);
    return ts.isIdentifier(map) && explicitMessageMaps.has(map.text);
  }
  return false;
}

function collectExplicitMessageMaps(sourceFile) {
  const maps = new Set();

  function visit(node) {
    if (
      ts.isVariableDeclaration(node) &&
      ts.isIdentifier(node.name) &&
      node.initializer &&
      ts.isVariableDeclarationList(node.parent) &&
      (node.parent.flags & ts.NodeFlags.Const) !== 0
    ) {
      const initializer = unwrapExpression(node.initializer);
      if (
        ts.isObjectLiteralExpression(initializer) &&
        initializer.properties.length > 0 &&
        initializer.properties.every((property) => {
          if (!ts.isPropertyAssignment(property)) return false;
          const value = unwrapExpression(property.initializer);
          return ts.isStringLiteralLike(value) && knownKeys.has(value.text);
        })
      ) {
        maps.add(node.name.text);
      }
    }
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  return maps;
}

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
  const explicitMessageMaps = collectExplicitMessageMaps(sourceFile);

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
      ((ts.isIdentifier(node.expression) && ["t", "rich"].includes(node.expression.text)) ||
        (ts.isPropertyAccessExpression(node.expression) &&
          ["t", "rich"].includes(node.expression.name.text)));
    if (
      isTranslationCall &&
      node.arguments.length > 0
    ) {
      const keyNode = node.arguments[0];
      const unwrappedKeyNode = unwrapExpression(keyNode);
      if (ts.isStringLiteralLike(unwrappedKeyNode) && !knownKeys.has(unwrappedKeyNode.text)) {
        const location = sourceFile.getLineAndCharacterOfPosition(keyNode.getStart(sourceFile));
        errors.push(
          `${relativePath}:${location.line + 1}:${location.character + 1} missing English key ${JSON.stringify(unwrappedKeyNode.text)}`,
        );
      } else if (!isAllowedTranslationKeyExpression(keyNode, explicitMessageMaps)) {
        const location = sourceFile.getLineAndCharacterOfPosition(keyNode.getStart(sourceFile));
        errors.push(
          `${relativePath}:${location.line + 1}:${location.character + 1} translation key must not be dynamically constructed; use a literal key or a typed explicit map`,
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
