import { copyFileSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const targets = {
  client: {
    appName: "Piano Academie Client",
    bundleId: "com.pianoacademie.client",
    configFile: "capacitor.client.config.json",
    envPrefix: "PA_CLIENT",
    defaultVersionName: "1.0",
    entitlementsPath: "App/App.entitlements",
  },
  prof: {
    appName: "Piano Academie Professeur",
    bundleId: "com.pianoacademie.professeur",
    configFile: "capacitor.prof.config.json",
    envPrefix: "PA_PROF",
    defaultVersionName: "1.0.0",
    entitlementsPath: '""',
  },
};

const targetName = process.argv[2];
const target = targets[targetName];

if (!target) {
  console.error("Usage: node scripts/prepare-ios-target.mjs <client|prof>");
  process.exit(1);
}

const rootDir = dirname(dirname(fileURLToPath(import.meta.url)));
const iosDir = join(rootDir, "ios", "App");
const appDir = join(iosDir, "App");
const plistPath = join(appDir, "Info.plist");
const projectPath = join(iosDir, "App.xcodeproj", "project.pbxproj");
const targetConfigPath = join(appDir, target.configFile);
const activeConfigPath = join(appDir, "capacitor.config.json");

function replaceOrFail(filePath, pattern, replacement, label) {
  const before = readFileSync(filePath, "utf8");
  const after = before.replace(pattern, replacement);
  const matched = pattern.global ? before.match(pattern) : pattern.test(before);
  if (!matched) {
    console.error(`Unable to update ${label} in ${filePath}`);
    process.exit(1);
  }
  writeFileSync(filePath, after);
}

replaceOrFail(
  plistPath,
  /(<key>CFBundleDisplayName<\/key>\s*<string>)([^<]+)(<\/string>)/,
  `$1${target.appName}$3`,
  "CFBundleDisplayName",
);

replaceOrFail(
  projectPath,
  /PRODUCT_BUNDLE_IDENTIFIER = com\.pianoacademie\.(client|professeur);/g,
  `PRODUCT_BUNDLE_IDENTIFIER = ${target.bundleId};`,
  "PRODUCT_BUNDLE_IDENTIFIER",
);

replaceOrFail(
  projectPath,
  /CODE_SIGN_ENTITLEMENTS = [^;]+;/g,
  `CODE_SIGN_ENTITLEMENTS = ${target.entitlementsPath};`,
  "CODE_SIGN_ENTITLEMENTS",
);

copyFileSync(targetConfigPath, activeConfigPath);

const versionName = process.env[`${target.envPrefix}_VERSION_NAME`] || target.defaultVersionName;
const versionCode = process.env[`${target.envPrefix}_VERSION_CODE`] || "1";
replaceOrFail(
  projectPath,
  /MARKETING_VERSION = [^;]+;/g,
  `MARKETING_VERSION = ${versionName};`,
  "MARKETING_VERSION",
);
replaceOrFail(
  projectPath,
  /CURRENT_PROJECT_VERSION = [^;]+;/g,
  `CURRENT_PROJECT_VERSION = ${versionCode};`,
  "CURRENT_PROJECT_VERSION",
);

console.log(`Prepared iOS target: ${target.appName} (${target.bundleId}) ${versionName} (${versionCode})`);
