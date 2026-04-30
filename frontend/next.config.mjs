function buildCsp(frameAncestors) {
  return [
    "default-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    `frame-ancestors ${frameAncestors}`,
    "img-src 'self' data: blob: https:",
    "font-src 'self' data: https:",
    "style-src 'self' 'unsafe-inline' https:",
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:",
    "connect-src 'self' https:",
    "form-action 'self' https:",
  ].join("; ");
}

const commonSecurityHeaders = [
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverActions: {
      bodySizeLimit: "2mb",
    },
  },
  async headers() {
    return [
      {
        source: "/embed/:path*",
        headers: [
          ...commonSecurityHeaders,
          { key: "Content-Security-Policy", value: buildCsp("'self' https:") },
        ],
      },
      {
        source: "/:path*",
        headers: [
          ...commonSecurityHeaders,
          { key: "Content-Security-Policy", value: buildCsp("'self'") },
        ],
      },
    ];
  },
};

export default nextConfig;
