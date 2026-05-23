import type { CapacitorConfig } from "@capacitor/cli";

type MobileTarget = "client" | "prof";

const rawTarget = process.env.MOBILE_APP_TARGET;
const target: MobileTarget = rawTarget === "prof" ? "prof" : "client";

const targetConfig: Record<MobileTarget, Pick<CapacitorConfig, "appId" | "appName" | "server">> = {
  client: {
    appId: "com.pianoacademie.client",
    appName: "Piano Academie Client",
    server: {
      url: "https://app.piano-academie.com/client",
      cleartext: false,
      allowNavigation: ["app.piano-academie.com"],
    },
  },
  prof: {
    appId: "com.pianoacademie.professeur",
    appName: "Piano Academie Professeur",
    server: {
      url: "https://app.piano-academie.com/prof",
      cleartext: false,
      allowNavigation: ["app.piano-academie.com"],
    },
  },
};

const config: CapacitorConfig = {
  ...targetConfig[target],
  webDir: "public",
  ios: {
    contentInset: "automatic",
    scrollEnabled: true,
  },
};

export default config;
