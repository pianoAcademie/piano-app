export function portalFailurePath(options: {
  status: number;
  returnTo: string;
  loginPath: string;
}): string {
  const { status, returnTo, loginPath } = options;
  if (status === 401) return loginPath;
  if (status === 403) {
    return `/access-denied?return_to=${encodeURIComponent(returnTo)}`;
  }
  return `/session-unavailable?return_to=${encodeURIComponent(returnTo)}`;
}
