import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = dirname(dirname(fileURLToPath(import.meta.url)));
const requestedTarget = process.argv[2];
const targets = requestedTarget === "client" || requestedTarget === "prof"
  ? [requestedTarget]
  : ["client", "prof"];
const definitions = {
  client: {
    appId: "com.pianoacademie.client",
    appName: "Piano Academie Client",
    url: "https://app.piano-academie.com/client",
    flavor: "client",
    signingPrefix: "PA_CLIENT",
  },
  prof: {
    appId: "com.pianoacademie.professeur",
    appName: "Piano Academie Professeur",
    url: "https://app.piano-academie.com/prof",
    flavor: "professeur",
    signingPrefix: "PA_PROF",
  },
};

const failures = [];
const requireFile = (relativePath) => {
  const absolutePath = join(rootDir, relativePath);
  if (!existsSync(absolutePath)) failures.push(`Missing ${relativePath}`);
  return absolutePath;
};
const readRequired = (relativePath) => {
  const path = requireFile(relativePath);
  return existsSync(path) ? readFileSync(path, "utf8") : "";
};

const gradle = readRequired("android/app/build.gradle");
const variables = readRequired("android/variables.gradle");
const manifest = readRequired("android/app/src/main/AndroidManifest.xml");
const mainActivity = readRequired("android/app/src/main/java/com/pianoacademie/mobile/MainActivity.java");
const iosProject = readRequired("ios/App/App.xcodeproj/project.pbxproj");
const iosAppDelegate = readRequired("ios/App/App/AppDelegate.swift");
const packageJson = JSON.parse(readRequired("package.json") || "{}");
const prepareIosTarget = readRequired("scripts/prepare-ios-target.mjs");

requireFile("android/gradlew");
requireFile("ios/App/App.xcworkspace/contents.xcworkspacedata");
requireFile("ios/App/App/PrivacyInfo.xcprivacy");
requireFile("ios/App/App/App.entitlements");
requireFile("public/app-icons/piano-academie-512.png");
requireFile("public/app-icons/piano-academie-professeur-1024-v2.png");
requireFile("public/app-icons/piano-academie-professeur-192.png");
requireFile("public/app-icons/piano-academie-professeur-512.png");
requireFile("app/client/manifest.webmanifest");
requireFile("app/prof/manifest.webmanifest");

const fileHash = (relativePath) => {
  const path = requireFile(relativePath);
  return existsSync(path) ? createHash("sha256").update(readFileSync(path)).digest("hex") : "";
};

const clientIosIconHash = fileHash("ios/App/App/Assets.xcassets/AppIcon.appiconset/AppIcon-512@2x.png");
const professorIosIconHash = fileHash("ios/App/App/Assets.xcassets/AppIconProf.appiconset/AppIconProf-512@2x.png");
const clientAndroidIconHash = fileHash("android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png");
const professorAndroidIconHash = fileHash("android/app/src/professeur/res/mipmap-xxxhdpi/ic_launcher.png");
const professorManifest = readRequired("app/prof/manifest.webmanifest/route.ts");

if (clientIosIconHash && clientIosIconHash === professorIosIconHash) {
  failures.push("iOS client and professor app icons must be distinct");
}
if (clientAndroidIconHash && clientAndroidIconHash === professorAndroidIconHash) {
  failures.push("Android client and professor app icons must be distinct");
}
if (!prepareIosTarget.includes('appIconName: "AppIcon"') || !prepareIosTarget.includes('appIconName: "AppIconProf"')) {
  failures.push("iOS target preparation must select a distinct client/professor icon set");
}
if (!packageJson.scripts?.["mobile:sync:prof:android"]?.includes("MOBILE_APP_TARGET=prof")) {
  failures.push("Android professor sync must use MOBILE_APP_TARGET=prof");
}
if (!professorManifest.includes("piano-academie-professeur-192.png") || !professorManifest.includes("piano-academie-professeur-512.png")) {
  failures.push("Professor installable web app must use the professor icon set");
}

for (const targetName of targets) {
  const target = definitions[targetName];
  const iosConfig = JSON.parse(readRequired(`ios/App/App/capacitor.${targetName === "prof" ? "prof" : "client"}.config.json`) || "{}");
  const androidConfig = JSON.parse(readRequired(`android/app/src/${target.flavor}/assets/capacitor.config.json`) || "{}");

  for (const [platform, config] of [["iOS", iosConfig], ["Android", androidConfig]]) {
    if (config.appId !== target.appId) failures.push(`${platform} ${targetName} appId must be ${target.appId}`);
    if (config.appName !== target.appName) failures.push(`${platform} ${targetName} appName must be ${target.appName}`);
    if (config.server?.url !== target.url) failures.push(`${platform} ${targetName} start URL must be ${target.url}`);
    if (config.server?.cleartext !== false) failures.push(`${platform} ${targetName} must reject cleartext traffic`);
  }

  if (!iosConfig.packageClassList?.includes("PushNotificationsPlugin")) {
    failures.push(`iOS ${targetName} must register PushNotificationsPlugin in packageClassList`);
  }
  if (!Array.isArray(iosConfig.plugins?.PushNotifications?.presentationOptions)) {
    failures.push(`iOS ${targetName} must configure foreground push presentation options`);
  }
  if (!Array.isArray(androidConfig.plugins?.PushNotifications?.presentationOptions)) {
    failures.push(`Android ${targetName} must configure foreground push presentation options`);
  }

  if (!gradle.includes(`${target.flavor} {`)) failures.push(`Android flavor ${target.flavor} is missing`);
  if (!gradle.includes(`applicationId "${target.appId}"`)) failures.push(`Android applicationId must include ${target.appId}`);
  if (!gradle.includes(`${target.signingPrefix}_KEYSTORE_PATH`)) failures.push(`Android ${targetName} signing must use ${target.signingPrefix}_* variables`);
}

if (!variables.includes("compileSdkVersion = 36")) failures.push("Android compile SDK must be API 36");
if (!variables.includes("targetSdkVersion = 36")) failures.push("Android target SDK must be API 36");
if (!manifest.includes('android:usesCleartextTraffic="false"')) failures.push("Android cleartext traffic must be disabled");
if (!manifest.includes('android:allowBackup="false"')) failures.push("Android backups must be disabled");
if (!mainActivity.includes("package com.pianoacademie.mobile;")) failures.push("Android MainActivity must use the shared namespace");

const releaseConfiguration = iosProject.match(/504EC3181FED79650016851F \/\* Release \*\/ = \{[\s\S]*?\n\t\t\};/u)?.[0] ?? "";
if (!releaseConfiguration.includes("CODE_SIGN_STYLE = Automatic;")) failures.push("iOS Release signing must be managed automatically by Xcode");
if (releaseConfiguration.includes("CODE_SIGN_IDENTITY =") || releaseConfiguration.includes("PROVISIONING_PROFILE_SPECIFIER =")) {
  failures.push("iOS Release signing must not force a certificate or provisioning profile");
}
if (!iosAppDelegate.includes(".capacitorDidRegisterForRemoteNotifications")) {
  failures.push("iOS APNs registration success must be forwarded to Capacitor");
}
if (!iosAppDelegate.includes(".capacitorDidFailToRegisterForRemoteNotifications")) {
  failures.push("iOS APNs registration errors must be forwarded to Capacitor");
}

for (const dependency of ["@capacitor/android", "@capacitor/cli", "@capacitor/core", "@capacitor/ios"]) {
  if (packageJson.devDependencies?.[dependency] !== "8.4.2") failures.push(`${dependency} must be pinned to 8.4.2`);
}
if (packageJson.dependencies?.["@capacitor/push-notifications"] !== "8.0.0") {
  failures.push("@capacitor/push-notifications must be pinned to 8.0.0");
}

if (failures.length > 0) {
  console.error("Mobile release configuration is not ready:");
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}

console.log(`Mobile release configuration: OK (${targets.join(", ")})`);
for (const targetName of targets) {
  const target = definitions[targetName];
  console.log(`- ${target.appName}: ${target.appId} -> ${target.url}`);
}
