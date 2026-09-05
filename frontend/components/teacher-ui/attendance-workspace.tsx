"use client";

import { Children, useEffect, useRef, useState, type ReactNode } from "react";
import { useFormStatus } from "react-dom";

/** Keep mounted student editors: navigating never discards an unsaved draft. */
export function StudentPager({ students, children, sessionId }: { students: { id: string; name: string }[]; children: ReactNode; sessionId: string }) {
  const [selected, setSelected] = useState(students[0]?.id);
  const [ready, setReady] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    try { const saved = sessionStorage.getItem(`attendance:${sessionId}`); if (saved) setSelected(saved); } catch { /* private browsing */ }
    setReady(true);
  }, [sessionId]);
  const index = Math.max(0, students.findIndex((student) => student.id === selected));
  function move(next: number) {
    if (root.current?.querySelector('[aria-busy="true"]')) return;
    const student = students[next];
    if (!student) return;
    setSelected(student.id);
    try { sessionStorage.setItem(`attendance:${sessionId}`, student.id); } catch { /* optional restoration */ }
    root.current?.closest(".teacher-attendance-body")?.scrollTo({ top: 0 });
  }
  return <div ref={root} className="teacher-student-pager">
    <nav className="teacher-student-navigation" aria-label="Navigation entre élèves">
      <button type="button" disabled={!ready || index === 0} onClick={() => move(index - 1)} aria-label="Élève précédent">←</button>
      <label><span aria-live="polite">Élève {index + 1} / {students.length}</span>
        <select disabled={!ready} aria-label="Élève affiché" value={students[index]?.id ?? ""} onChange={(e) => move(students.findIndex((s) => s.id === e.target.value))}>
          {students.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </label>
      <button type="button" disabled={!ready || index >= students.length - 1} onClick={() => move(index + 1)} aria-label="Élève suivant">→</button>
    </nav>
    {Children.toArray(children).map((child, i) => <div key={students[i]?.id ?? i} hidden={i !== index}>{child}</div>)}
  </div>;
}

export function AttendanceButton({ children, className }: { children: ReactNode; className: string }) {
  const { pending } = useFormStatus();
  return <button type="submit" className={className} disabled={pending} aria-busy={pending}>{pending ? "Enregistrement…" : children}</button>;
}

export function AttendanceDialog({ children, closeHref }: { children: ReactNode; closeHref: string }) {
  const root = useRef<HTMLElement>(null);
  const [closing, setClosing] = useState(false);
  const leaving = useRef(false);
  function dirty() {
    if (leaving.current) return false;
    return Boolean(root.current?.querySelector('[data-learning-draft="true"]')) ||
      Array.from(root.current?.querySelectorAll("textarea") ?? []).some((field) => field.value !== field.defaultValue);
  }
  function close() {
    if (root.current?.querySelector('[aria-busy="true"]')) { window.alert("Veuillez attendre la fin de l’enregistrement."); return; }
    if (dirty() && !window.confirm("Des modifications ne sont pas enregistrées. Fermer sans les enregistrer ?")) return;
    leaving.current = true;
    setClosing(true);
    // A real navigation avoids waiting silently on a suspended server-component transition.
    window.location.assign(closeHref);
  }
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const beforeUnload = (event: BeforeUnloadEvent) => { if (dirty()) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", beforeUnload);
    root.current?.querySelector<HTMLElement>(".modal-close-x")?.focus();
    return () => { document.body.style.overflow = previous; window.removeEventListener("beforeunload", beforeUnload); };
  }, []);
  return <section ref={root} role="dialog" aria-modal="true" aria-label="Présences et progression des élèves"
    className="modal-overlay modal-overlay-front teacher-attendance-overlay"
    onSubmitCapture={(event) => {
      const form = event.target as HTMLFormElement;
      // In the "missing" filter, saving attendance removes the student from the
      // server roster. Do not discard a pedagogical draft in that transition.
      if (form.elements?.namedItem("attendance_status") && dirty()) {
        event.preventDefault(); event.stopPropagation();
        window.alert("Enregistrez ou annulez vos modifications en cours avant de modifier la présence.");
      }
    }}
    onClickCapture={(event) => {
      const link = (event.target as HTMLElement).closest("a");
      if (link?.getAttribute("href") === closeHref) { event.preventDefault(); event.stopPropagation(); close(); }
      else if (link && (root.current?.querySelector('[aria-busy="true"]') ||
        (dirty() && !window.confirm("Des modifications ne sont pas enregistrées. Quitter cette saisie ?")))) {
        event.preventDefault(); event.stopPropagation();
      }
    }} onKeyDown={(event) => {
      if (event.key === "Escape") { event.preventDefault(); close(); }
      if (event.key === "Tab") {
        const controls = Array.from(root.current?.querySelectorAll<HTMLElement>('a[href], button:not(:disabled), select, textarea, input:not([type="hidden"]), summary') ?? []).filter((el) => el.getClientRects().length);
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    }}>
    {closing ? <p role="status" className="teacher-closing">Retour au planning…</p> : children}
  </section>;
}
