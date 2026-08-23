"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function MobileDefaultAgendaView(): null {
  const router = useRouter();

  useEffect(() => {
    if (!window.matchMedia("(max-width: 760px)").matches) {
      return;
    }

    const url = new URL(window.location.href);
    if (url.searchParams.has("agenda_view")) {
      return;
    }

    url.searchParams.set("agenda_view", "week");
    router.replace(`${url.pathname}?${url.searchParams.toString()}${url.hash}`, { scroll: false });
  }, [router]);

  return null;
}
