import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = dirname(dirname(fileURLToPath(import.meta.url)));
const expected = {
  appId: "com.pianoacademie.professeur",
  appName: "Piano Academie Professeur",
  url: "https://app.piano-academie.com/prof",
};

const failures = [];
const requireFile = (relativePath) => {
  const absolutePath = join(rootDir, relativePath);
  if (!existsSync(absolutePath)) {
    failures.push(`Missing ${relativePath}`);
  }
  return absolutePath;
};

const capacitorConfigPath = requireFile("ios/App/App/capacitor.prof.config.json");
const androidGradlePath = requireFile("android/app/build.gradle");
const androidStringsPath = requireFile("android/app/src/main/res/values/strings.xml");
const androidVariablesPath = requireFile("android/variables.gradle");
const packagePath = requireFile("package.json");
requireFile("android/gradlew");
requireFile("ios/App/App.xcworkspace/contents.xcworkspacedata");
requireFile("public/app-icons/piano-academie-512.png");
requireFile("public/prof-sw.js");

if (existsSync(capacitorConfigPath)) {
  const config = JSON.parse(readFileSync(capacitorConfigPath, "utf8"));
  if (config.appId !== expected.appId) failures.push(`iOS appId must be ${expected.appId}`);
  if (config.appName !== expected.appName) failures.push(`iOS appName must be ${expected.appName}`);
  if (config.server?.url !== expected.url) failures.push(`iOS start URL must be ${expected.url}`);
}

if (existsSync(androidGradlePath)) {
  const gradle = readFileSync(androidGradlePath, "utf8");
  if (!gradle.includes(`applicationId "${expected.appId}"`)) failures.push(`Android applicationId must be ${expected.appId}`);
  if (!gradle.includes("PA_PROF_KEYSTORE_PATH")) failures.push("Android release signing must use environment variables");
}

if (existsSync(androidStringsPath)) {
  const strings = readFileSync(androidStringsPath, "utf8");
  if (!strings.includes(`<string name="app_name">${expected.appName}</string>`)) failures.push(`Android app name must be ${expected.appName}`);
}

if (existsSync(androidVariablesPath)) {
  const variables = readFileSync(androidVariablesPath, "utf8");
  if (!variables.includes("compileSdkVersion = 36")) failures.push("Android compile SDK must be API 36");
  if (!variables.includes("targetSdkVersion = 36")) failures.push("Android target SDK must be API 36");
}

if (existsSync(packagePath)) {
  const packageJson = JSON.parse(readFileSync(packagePath, "utf8"));
  for (const dependency of ["@capacitor/android", "@capacitor/cli", "@capacitor/core", "@capacitor/ios"]) {
    if (packageJson.devDependencies?.[dependency] !== "8.4.2") failures.push(`${dependency} must be pinned to 8.4.2`);
  }
}

if (failures.length > 0) {
  console.error("Professor mobile release is not ready:");
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}

console.log("Professor mobile release configuration: OK");
console.log(`- ${expected.appName}`);
console.log(`- ${expected.appId}`);
console.log(`- ${expected.url}`);
