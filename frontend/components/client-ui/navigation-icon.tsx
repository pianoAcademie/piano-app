import type { ReactNode } from "react";

export type ClientNavigationIconName =
  | "home"
  | "calendar"
  | "book"
  | "receipt"
  | "card"
  | "mail"
  | "news"
  | "user"
  | "ticket"
  | "phone"
  | "bell"
  | "chat"
  | "pin"
  | "location";

export default function ClientNavigationIcon({
  name,
  className = "",
}: {
  name: ClientNavigationIconName;
  className?: string;
}): JSX.Element {
  let content: ReactNode;

  switch (name) {
    case "home":
      content = <><path d="m3 10.5 9-7.5 9 7.5" /><path d="M5.5 9.5V21h13V9.5" /><path d="M9 21v-6h6v6" /></>;
      break;
    case "calendar":
      content = <><path d="M7 3v4M17 3v4M4 9h16" /><rect x="4" y="5" width="16" height="16" rx="2" /></>;
      break;
    case "book":
      content = <><path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H12v18H7.5A3.5 3.5 0 0 0 4 23V5.5Z" /><path d="M20 5.5A3.5 3.5 0 0 0 16.5 2H12v18h4.5A3.5 3.5 0 0 1 20 23V5.5Z" /></>;
      break;
    case "receipt":
      content = <><path d="M6 3h12v19l-3-2-3 2-3-2-3 2V3Z" /><path d="M9 8h6M9 12h6M9 16h4" /></>;
      break;
    case "card":
      content = <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 10h18M7 15h4" /></>;
      break;
    case "mail":
      content = <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m4 7 8 6 8-6" /></>;
      break;
    case "news":
      content = <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M7 8h5v5H7zM15 8h3M15 12h3M7 16h11" /></>;
      break;
    case "user":
      content = <><circle cx="12" cy="8" r="4" /><path d="M4.5 21a7.5 7.5 0 0 1 15 0" /></>;
      break;
    case "ticket":
      content = <><path d="M4 6h16v4a2 2 0 0 0 0 4v4H4v-4a2 2 0 0 0 0-4V6Z" /><path d="M12 7.5v9" /></>;
      break;
    case "phone":
      content = <path d="M7 3H4.5A1.5 1.5 0 0 0 3 4.5C3 13.6 10.4 21 19.5 21a1.5 1.5 0 0 0 1.5-1.5V17l-4-1-1.5 2a14 14 0 0 1-9.5-9.5L8 7 7 3Z" />;
      break;
    case "bell":
      content = <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></>;
      break;
    case "chat":
      content = <path d="M4 4h16v12H9l-5 4V4Z" />;
      break;
    case "pin":
      content = <><path d="m9 3 6 6M14 4l6 6-4 1-4 5-1 4-2-2-4 3 3-4-2-2 4-1 5-4-1-4Z" /></>;
      break;
    case "location":
      content = <><path d="M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></>;
      break;
  }

  return (
    <svg
      className={`client-navigation-icon ${className}`.trim()}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {content}
    </svg>
  );
}
