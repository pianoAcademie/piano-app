"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

type Props = {
  editHref: string;
  viewCompositionHref: string;
  kitId: string;
  returnTo: string;
  active: boolean;
  duplicateAction: (formData: FormData) => void | Promise<void>;
  toggleArchiveAction: (formData: FormData) => void | Promise<void>;
  deleteAction: (formData: FormData) => void | Promise<void>;
};

type MenuPosition = {
  top: number;
  left: number;
};

const MENU_MIN_WIDTH = 210;
const VIEWPORT_PADDING = 8;

export default function AdminKitActionsMenu({
  editHref,
  viewCompositionHref,
  kitId,
  returnTo,
  active,
  duplicateAction,
  toggleArchiveAction,
  deleteAction,
}: Props): JSX.Element {
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<MenuPosition>({ top: 0, left: 0 });

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open) {
      return;
    }

    const updatePosition = (): void => {
      const trigger = triggerRef.current;
      if (!trigger) {
        return;
      }
      const rect = trigger.getBoundingClientRect();
      const menuHeight = panelRef.current?.offsetHeight ?? 220;
      const placeAbove = rect.bottom + menuHeight + VIEWPORT_PADDING > window.innerHeight;
      const top = placeAbove ? Math.max(VIEWPORT_PADDING, rect.top - menuHeight - 8) : rect.bottom + 8;
      const left = Math.min(
        Math.max(VIEWPORT_PADDING, rect.right - MENU_MIN_WIDTH),
        Math.max(VIEWPORT_PADDING, window.innerWidth - MENU_MIN_WIDTH - VIEWPORT_PADDING),
      );
      setPosition({ top, left });
    };

    const handlePointer = (event: MouseEvent): void => {
      const target = event.target as Node | null;
      if (!target) {
        return;
      }
      if (panelRef.current?.contains(target) || triggerRef.current?.contains(target)) {
        return;
      }
      setOpen(false);
    };

    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const portal = useMemo(() => {
    if (!mounted || !open) {
      return null;
    }
    return createPortal(
      <div
        ref={panelRef}
        className="catalog-actions-portal"
        style={{ top: `${position.top}px`, left: `${position.left}px` }}
        role="menu"
        aria-label="Actions kit"
      >
        <Link href={editHref} className="catalog-actions-item" role="menuitem" onClick={() => setOpen(false)}>
          Modifier
        </Link>
        <form action={duplicateAction} onSubmit={() => setOpen(false)}>
          <input type="hidden" name="kit_id" value={kitId} />
          <input type="hidden" name="return_to" value={returnTo} />
          <button type="submit" className="catalog-actions-item" role="menuitem">
            Dupliquer
          </button>
        </form>
        <form action={toggleArchiveAction} onSubmit={() => setOpen(false)}>
          <input type="hidden" name="kit_id" value={kitId} />
          <input type="hidden" name="archive" value={active ? "true" : "false"} />
          <input type="hidden" name="return_to" value={returnTo} />
          <button type="submit" className="catalog-actions-item" role="menuitem">
            {active ? "Archiver" : "Desarchiver"}
          </button>
        </form>
        <form action={deleteAction} onSubmit={() => setOpen(false)}>
          <input type="hidden" name="kit_id" value={kitId} />
          <input type="hidden" name="return_to" value={returnTo} />
          <button type="submit" className="catalog-actions-item danger" role="menuitem">
            Supprimer
          </button>
        </form>
        <Link href={viewCompositionHref} className="catalog-actions-item" role="menuitem" onClick={() => setOpen(false)}>
          Voir composition
        </Link>
      </div>,
      document.body,
    );
  }, [
    mounted,
    open,
    position.left,
    position.top,
    editHref,
    viewCompositionHref,
    duplicateAction,
    toggleArchiveAction,
    deleteAction,
    kitId,
    returnTo,
    active,
  ]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="ghost catalog-actions-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        ⋯
      </button>
      {portal}
    </>
  );
}
